import os
import logging
import time
from flask import Flask, send_from_directory, request, jsonify, abort, Response
from flask_cors import CORS
import requests
from mcp_processor import APIQueryProcessor, QueryResponse, QueryRequest
from local_settings import settings
from dataset_service import (
    list_datasets,
    get_dataset,
    get_records,
    patch_record_markdown,
    ingest_dataset,
    ensure_indexes,
)
from mongomcp.datasets.discovery import discover_cluster_datasets
from mongomcp import __version__ as MCP_VERSION
import mimetypes
import traceback
from typing import Optional, List, Any
import threading
import json
import queue

logging.basicConfig(level=logging.INFO)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

mimetypes.add_type('application/javascript', '.js')

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'frontend', 'dist'))
CORS(app)

processor = APIQueryProcessor()
_site_warmup_lock = threading.Lock()
_site_warmup_done = False


def _warmup_tool_discovery_once() -> None:
    """Run MCP tool discovery once on first site load, retrying until tools are found."""
    global _site_warmup_done
    if _site_warmup_done:
        return
    with _site_warmup_lock:
        if _site_warmup_done:
            return
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                # If tools already loaded (e.g. __init__ succeeded), we're done.
                if processor.mcp_tools_config:
                    _site_warmup_done = True
                    return
                # Tools not yet discovered — trigger discovery now.
                processor._discover_tools()
                if processor.mcp_tools_config:
                    _site_warmup_done = True
                    return
            except Exception:
                traceback.print_exc()

            if attempt >= max_attempts:
                # Do not block initial page load on warmup failure.
                app.logger.warning("Warmup tool discovery failed after %s attempts.", max_attempts)
                return
            wait_seconds = attempt * 5
            app.logger.warning(
                "Warmup tool discovery returned no tools (attempt %s/%s). Retrying in %ss.",
                attempt,
                max_attempts,
                wait_seconds,
            )
            time.sleep(wait_seconds)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "version": MCP_VERSION,
        "processor_ready": processor.init_error is None,
    }), 200


@app.route('/query', methods=['POST'])
def api_query():
    resp = '{"status": "error", "message": "Unknown error"}'  # Default error response
    code = 500
    try:
        payload = request.get_json(force=True)

        if processor.init_error:
            raise ValueError(f"Processor initialization failed: {processor.init_error}")

        q = (payload.get("input", "") or "").strip()
        if not q:
            raise ValueError("Empty input")

        req = QueryRequest(input=q, history=payload.get("history", []), user_id=payload.get("user_id"), username=payload.get("username"), session_id=payload.get("session_id"))
        resp = processor.query_with_mcp_tools(req).json()
        code = 200

    except Exception as e:
        traceback.print_exc()
        resp = QueryResponse(status="Error", error=str(e)).json()

    return jsonify(resp), code


@app.route('/query/stream', methods=['POST'])
def stream_query():
    """Stream the response for long-running queries."""
    # Read request payload here while request context is active
    try:
        payload = request.get_json(force=True)
        # Pass a copy of payload into generator to avoid accessing `request` inside it
        return Response(generate(payload), mimetype='application/x-ndjson')
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/reset', methods=['POST'])
def full_reset():
    """Full application reset: clear state, drop cached MCP clients, reload tool discovery."""
    try:
        if processor.init_error:
            raise ValueError(f"Processor initialization failed: {processor.init_error}")
        resp = processor.reset().json()
        return jsonify(resp), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify(QueryResponse(status="Error", error=str(e)).json()), 500


@app.route('/pattern/save', methods=['POST'])
def save_pattern():
    """Save the current interaction as a reusable query pattern."""
    try:
        if processor.init_error:
            raise ValueError(f"Processor initialization failed: {processor.init_error}")
        payload = request.get_json(force=True) or {}
        user_id = (payload.get("user_id") or "").strip()
        session_id = (payload.get("session_id") or "").strip()
        history = payload.get("history") or []
        resp = processor.save_pattern(user_id, session_id, history)
        return jsonify(resp.json()), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify(QueryResponse(status="Error", error=str(e)).json()), 500


@app.route('/feedback', methods=['POST'])
def record_feedback():
    """Record user feedback (positive/negative) on the last interaction."""
    try:
        if processor.init_error:
            raise ValueError(f"Processor initialization failed: {processor.init_error}")
        payload = request.get_json(force=True)
        user_id = (payload.get("user_id") or "").strip()
        session_id = (payload.get("session_id") or "").strip()
        feedback = (payload.get("feedback") or "").strip()
        history = payload.get("history") or []
        if not user_id or not session_id or feedback not in ("positive", "negative"):
            return jsonify({"error": "user_id, session_id, and feedback (positive|negative) required"}), 400
        resp = processor.record_feedback(user_id, session_id, feedback, history)
        return jsonify(resp.json()), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify(QueryResponse(status="Error", error=str(e)).json()), 500

def generate(payload):
    try:
        if processor.init_error:
            yield QueryResponse(error=f"Processor initialization failed: {processor.init_error}").json() + '\n'
            return

        q = (payload.get("input", "") or "").strip()
        if not q:
            yield QueryResponse(status="Error", error="Empty input").json() + '\n'
            return

        local_queue = queue.Queue()

        def emit_local(message, status="Processing"):
            if isinstance(message, Exception):
                resp = QueryResponse(status="Error", error=str(message), message=str(message))
            else:
                resp = QueryResponse(status=status, message=str(message))
            local_queue.put(resp.json())

        def read_local_stream(timeout=0.1):
            while True:
                try:
                    yield local_queue.get(timeout=timeout)
                except queue.Empty:
                    break

        def pop_local_messages() -> List[str]:
            msgs = []
            while True:
                try:
                    msgs.append(local_queue.get_nowait())
                except queue.Empty:
                    break
            return msgs

        # Generic threaded executor - returns (result, exception)
        def execute_in_thread(func):
            """Execute a function in a background thread and stream messages."""
            result = [None]
            exception = [None]

            def wrapper():
                try:
                    result[0] = func()
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=wrapper, daemon=True)
            thread.start()

            HEARTBEAT_INTERVAL = 5.0
            last_heartbeat = time.monotonic()

            # Stream messages as they arrive from the handler
            while thread.is_alive():
                for msg in read_local_stream(timeout=0.1):
                    yield msg + '\n'
                    last_heartbeat = time.monotonic()

                if time.monotonic() - last_heartbeat >= HEARTBEAT_INTERVAL:
                    # Drain queue first, then emit heartbeat
                    for msg in pop_local_messages():
                        yield msg + '\n'
                    yield QueryResponse(status='LLM Thinking...', message='LLM is still thinking...').json() + '\n'
                    last_heartbeat = time.monotonic()

            # Drain any remaining messages after thread completes
            for msg in pop_local_messages():
                yield msg + '\n'

            # Yield the final result and exception as a tuple
            yield (result[0], exception[0])

        result = None
        exception = None

        yield QueryResponse(status='querying', message='Querying Claude with MCP tools...').json() + '\n'
        req = QueryRequest(input=q, history=payload.get("history", []), user_id=payload.get("user_id"), username=payload.get("username"), session_id=payload.get("session_id"))
        for item in execute_in_thread(lambda: processor.query_with_mcp_tools(req, emit=emit_local)):
            if isinstance(item, tuple):
                result, exception = item
            else:
                yield item

        # Yield final result
        if exception:
            yield QueryResponse(error=str(exception)).json() + '\n'
        elif result:
            yield result.json() + '\n'

    except Exception as e:
        traceback.print_exc()
        yield QueryResponse(error=str(e)).json() + '\n'


def _dataset_progress_json(stage: str, message: str, extra: Optional[dict] = None) -> str:
  payload = {"stage": stage, "message": message}
  if extra:
    payload.update(extra)
  return json.dumps(payload) + "\n"


def _execute_streaming_job(func):
    """Run func in a background thread; yield NDJSON lines from its emit queue."""
    local_queue = queue.Queue()
    result = [None]
    exception = [None]

    def emit(stage, message, extra=None):
        local_queue.put(_dataset_progress_json(stage, message, extra))

    def wrapper():
        try:
            result[0] = func(emit)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()

    while thread.is_alive():
        try:
            yield local_queue.get(timeout=0.1)
        except queue.Empty:
            continue

    while not local_queue.empty():
        yield local_queue.get()

    if exception[0]:
        yield json.dumps({"stage": "error", "message": str(exception[0])}) + "\n"
    elif result[0] is not None:
        yield json.dumps({"stage": "complete", "message": "Upload complete", **result[0]}, default=str) + "\n"


def _parse_upload_params():
    """Extract upload fields from multipart form or JSON body."""
    if request.content_type and "multipart/form-data" in request.content_type:
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        category = (request.form.get("category") or "").strip()
        username = (request.form.get("username") or "").strip()
        text = (request.form.get("text") or "").strip()
        upload_file = request.files.get("file")
        raw_content = None
        filename = ""
        if upload_file and upload_file.filename:
            raw_content = upload_file.read()
            filename = upload_file.filename
        elif text:
            raw_content = text
        return name, description, category, username, raw_content, filename

    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    category = (payload.get("category") or "").strip()
    username = (payload.get("username") or "").strip()
    text = (payload.get("text") or "").strip()
    raw_content = text if text else None
    return name, description, category, username, raw_content, ""


@app.route('/admin/datasets/discover', methods=['POST'])
def admin_discover_datasets():
    """Scan cluster collections and register datasets (skips admin/local/config/mcp_config)."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        force_refresh = bool(payload.get("force_refresh"))
        summary = discover_cluster_datasets(settings, force_refresh=force_refresh)
        return jsonify(summary), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/datasets', methods=['GET'])
def admin_list_datasets():
    try:
        return jsonify({"datasets": list_datasets()}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/datasets/<dataset_id>', methods=['GET'])
def admin_get_dataset(dataset_id):
    try:
        ds = get_dataset(dataset_id)
        if not ds:
            return jsonify({"error": "Dataset not found"}), 404
        return jsonify(ds), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/datasets/<dataset_id>/records', methods=['GET'])
def admin_get_records(dataset_id):
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        return jsonify(get_records(dataset_id, page=page, limit=limit)), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/datasets/<dataset_id>/records/<record_id>', methods=['PATCH'])
def admin_patch_record(dataset_id, record_id):
    try:
        payload = request.get_json(force=True) or {}
        username = (payload.get("username") or "").strip()
        display_markdown = payload.get("display_markdown")
        if not username:
            return jsonify({"error": "username required"}), 400
        if display_markdown is None:
            return jsonify({"error": "display_markdown required"}), 400
        record = patch_record_markdown(dataset_id, record_id, username, display_markdown)
        return jsonify(record), 200
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/admin/datasets/upload/stream', methods=['POST'])
def admin_upload_dataset_stream():
    try:
        name, description, category, username, raw_content, filename = _parse_upload_params()
        if raw_content is None:
            return jsonify({"error": "file or text content required"}), 400

        def job(emit):
            return ingest_dataset(
                name=name,
                description=description,
                category=category,
                owner=username,
                raw_content=raw_content,
                filename=filename,
                emit=emit,
            )

        return Response(_execute_streaming_job(job), mimetype='application/x-ndjson')
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


try:
    ensure_indexes()
except Exception:
    app.logger.warning("Could not ensure admin dataset indexes on startup", exc_info=True)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder = app.static_folder
    app.logger.debug("serve: static_folder=%s", static_folder)
    if path != "" and os.path.exists(os.path.join(static_folder, path)):
        return send_from_directory(static_folder, path)
    index_path = os.path.join(static_folder, 'index.html')
    if os.path.exists(index_path):
        _warmup_tool_discovery_once()
        return send_from_directory(static_folder, 'index.html')
    return "Frontend not found. you must first build the project.", 404


if __name__ == '__main__':
    debug = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    app.run(host='0.0.0.0', port=8001, debug=debug)
