import json
import math
import os
import resource
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("DOCUMENT_PARSER_SOCKET_PATH", "/run/gabflow-parser/parser.sock"))
MAX_REQUEST_BYTES = 8192
WORKER_SLOTS = threading.BoundedSemaphore(int(os.environ.get("PARSER_MAX_WORKERS", "4")))


def main() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o660)
        server.listen(int(os.environ.get("PARSER_MAX_QUEUE", "16")))
        while True:
            connection, _ = server.accept()
            threading.Thread(
                target=_handle_connection,
                args=(connection,),
                daemon=True,
            ).start()


def _handle_connection(connection: socket.socket) -> None:
    with connection:
        try:
            request_size = struct.unpack("!I", _receive_exact(connection, 4))[0]
            if request_size <= 0 or request_size > MAX_REQUEST_BYTES:
                raise ValueError("Solicitacao excede o limite do parser.")
            request = _receive_exact(connection, request_size)
            if not WORKER_SLOTS.acquire(timeout=1):
                raise RuntimeError("Parser isolado esta temporariamente ocupado.")
            try:
                response = _run_worker(request)
            finally:
                WORKER_SLOTS.release()
        except Exception as error:
            response = json.dumps(
                {
                    "status": "ERROR",
                    "code": "PARSER_SERVICE_ERROR",
                    "message": str(error).replace("\n", " ")[:500],
                    "retryable": True,
                },
                separators=(",", ":"),
            ).encode()
        connection.sendall(struct.pack("!I", len(response)) + response)


def _run_worker(request: bytes) -> bytes:
    timeout = float(os.environ.get("PARSER_TIMEOUT_SECONDS", "120"))
    maximum_response = int(os.environ.get("PARSER_MAX_RESPONSE_BYTES", "10485760"))
    environment = {
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PARSER_ALLOWED_ROOTS": os.environ.get(
            "PARSER_ALLOWED_ROOTS", "/app/data/attachments:/app/data/rag"
        ),
        "PARSER_MAX_FILE_BYTES": os.environ.get("PARSER_MAX_FILE_BYTES", "31457280"),
        "PARSER_MAX_OUTPUT_CHARS": os.environ.get("PARSER_MAX_OUTPUT_CHARS", "5000000"),
        "DOCUMENT_OCR_MODEL": os.environ.get("DOCUMENT_OCR_MODEL", "tesseract-5"),
        "DOCUMENT_OCR_LANGUAGE": os.environ.get("DOCUMENT_OCR_LANGUAGE", "por"),
        "DOCUMENT_OCR_MAX_PAGES": os.environ.get("DOCUMENT_OCR_MAX_PAGES", "500"),
        "DOCUMENT_OCR_MAX_PIXELS": os.environ.get("DOCUMENT_OCR_MAX_PIXELS", "25000000"),
        "DOCUMENT_OCR_NATIVE_MIN_CHARS": os.environ.get("DOCUMENT_OCR_NATIVE_MIN_CHARS", "40"),
        "DOCUMENT_OCR_BATCH_SIZE": os.environ.get("DOCUMENT_OCR_BATCH_SIZE", "8"),
    }
    completed = subprocess.run(  # noqa: S603 - executavel e argumentos fixos
        [sys.executable, "-I", "/app/app/rag/parser_worker.py"],
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=environment,
        timeout=timeout,
        check=False,
        preexec_fn=lambda: _set_limits(timeout),
    )
    if completed.returncode != 0 or not completed.stdout:
        raise RuntimeError("Subprocesso de parsing terminou sem resposta valida.")
    if len(completed.stdout) > maximum_response:
        raise RuntimeError("Subprocesso de parsing excedeu o limite de resposta.")
    return completed.stdout


def _set_limits(timeout: float) -> None:
    memory_bytes = int(os.environ.get("PARSER_PROCESS_MEMORY_BYTES", "536870912"))
    cpu_seconds = max(1, math.ceil(timeout))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise OSError("Conexao encerrada durante a requisicao.")
        result.extend(chunk)
    return bytes(result)


if __name__ == "__main__":
    main()
