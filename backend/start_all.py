from __future__ import annotations

import os
import json
import socket
import subprocess
import shutil
import sys
import time
import webbrowser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import (
    DEFAULT_BACKEND_ADMIN_PORT,
    DEFAULT_EDUCATION_API_PORT,
    DEFAULT_FRONTEND_PORT,
    DEFAULT_MAINTENANCE_API_PORT,
    build_service_base_url,
    get_env,
    get_env_int,
    get_loopback_host,
    load_root_env,
    write_frontend_json_cache,
    write_frontend_runtime_config,
)


BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_CONFIG_PATH = FRONTEND_DIR / "env-config.js"
FRONTEND_CHAPTER_CACHE_PATH = FRONTEND_DIR / "chapters-cache.json"
BACKEND_CHAPTERS_PATH = BACKEND_DIR / "data" / "chapters.json"
BACKEND_ADMIN_PATH = BACKEND_DIR / "vector_index_system" / "backend_admin.py"
RUNTIME_DIR = ROOT_DIR / ".runtime"
LOG_DIR = RUNTIME_DIR / "logs"
PID_FILE = RUNTIME_DIR / "knowledge-gragph-teaching-system-processes.json"
WINDOWS_CREATE_FLAGS = 0
LOG_HANDLES = []


def resolve_executable(value: str) -> str | None:
    expanded = os.path.expandvars(os.path.expanduser(value.strip()))
    if not expanded:
        return None

    path = Path(expanded)
    if path.exists():
        return str(path)

    found = shutil.which(expanded)
    if found:
        return found

    return None


def get_runtime_python() -> str:
    for env_name in ("PYTHON_EXE", "CONDA_ENV_PYTHON"):
        configured = get_env(env_name, "")
        resolved = resolve_executable(configured)
        if resolved:
            return resolved

    conda_root = get_env("CONDA_ROOT", "")
    conda_env_name = get_env("CONDA_ENV_NAME", get_env("ENV_NAME", ""))
    if conda_root and conda_env_name:
        resolved = resolve_executable(str(Path(conda_root) / "envs" / conda_env_name / "python.exe"))
        if resolved:
            return resolved

    conda_prefix = get_env("CONDA_PREFIX", "")
    if conda_prefix:
        resolved = resolve_executable(str(Path(conda_prefix) / "python.exe"))
        if resolved:
            return resolved

    return sys.executable


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((get_loopback_host(), port)) == 0


def require_free_port(port: int, description: str) -> None:
    if is_port_in_use(port):
        raise RuntimeError(
            f"{description} 端口 {port} 已被占用。请先关闭旧服务，或运行 .\\stop.ps1。"
        )


def start_managed_process(
    name: str,
    args: list[str],
    *,
    cwd: Path | None,
    port: int,
    description: str,
) -> subprocess.Popen[bytes]:
    ensure_runtime_dirs()
    require_free_port(port, description)

    out_log = LOG_DIR / f"{name}.out.log"
    err_log = LOG_DIR / f"{name}.err.log"
    stdout_handle = open(out_log, "ab", buffering=0)
    stderr_handle = open(err_log, "ab", buffering=0)
    LOG_HANDLES.extend([stdout_handle, stderr_handle])

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"正在启动 {description} ...")
    process = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=WINDOWS_CREATE_FLAGS,
        env=env,
    )

    print(f"[OK] {description} 已启动，PID: {process.pid}")
    print(f"     日志: {out_log}")
    return process


def start_api_server(api_path: Path, port: int, description: str) -> subprocess.Popen[bytes]:
    process = start_managed_process(
        description.replace(" ", "-").lower(),
        [get_runtime_python(), str(api_path)],
        cwd=api_path.parent,
        port=port,
        description=description,
    )

    host = get_loopback_host()
    print(f"     服务: http://{host}:{port}")
    print(f"     文档: http://{host}:{port}/docs")
    time.sleep(1)
    return process


def start_frontend_server(port: int) -> subprocess.Popen[bytes]:
    process = start_managed_process(
        "frontend",
        [get_runtime_python(), str(BACKEND_DIR / "frontend_server.py"), str(port), str(FRONTEND_DIR)],
        cwd=ROOT_DIR,
        port=port,
        description="前端页面服务",
    )

    print(f"     服务: http://{get_loopback_host()}:{port}")
    time.sleep(1)
    return process


def start_backend_admin_server(port: int) -> subprocess.Popen[bytes]:
    process = start_managed_process(
        "backend-admin",
        [get_runtime_python(), str(BACKEND_ADMIN_PATH), "--port", str(port)],
        cwd=BACKEND_ADMIN_PATH.parent,
        port=port,
        description="后端知识图谱管理页",
    )

    print(f"     服务: http://{get_loopback_host()}:{port}")
    time.sleep(1)
    return process


def stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    print("\n正在停止服务...")
    for name, process in processes.items():
        try:
            if process.poll() is None:
                print(f"  停止 {name} ...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                    print(f"[OK] {name} 已停止")
                except subprocess.TimeoutExpired:
                    process.kill()
                    print(f"[OK] {name} 已强制停止")
            else:
                print(f"  {name} 已退出")
        except Exception as exc:
            print(f"[WARNING] 停止 {name} 失败: {exc}")


def close_logs() -> None:
    while LOG_HANDLES:
        handle = LOG_HANDLES.pop()
        try:
            handle.close()
        except Exception:
            pass


def write_pid_file(processes: dict[str, subprocess.Popen[bytes]], ports: dict[str, int]) -> None:
    ensure_runtime_dirs()
    payload = [
        {"name": name, "pid": process.pid, "port": ports.get(name)}
        for name, process in processes.items()
    ]
    PID_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def generate_frontend_cache() -> None:
    payload = {"chapters": {}}
    if BACKEND_CHAPTERS_PATH.exists():
        try:
            import json

            payload = json.loads(BACKEND_CHAPTERS_PATH.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {"chapters": {}}
        except Exception as exc:
            print(f"[WARNING] Failed to build chapter cache: {exc}")
            payload = {"chapters": {}}

    write_frontend_json_cache(FRONTEND_CHAPTER_CACHE_PATH, payload)


def should_auto_open_browser() -> bool:
    value = os.getenv("AUTO_OPEN_BROWSER", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def open_frontend_home(frontend_base_url: str) -> None:
    target = f"{frontend_base_url.rstrip('/')}/"
    if not should_auto_open_browser():
        print(f"[INFO] Auto-open disabled. Open manually: {target}")
        return

    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            webbrowser.open(target, new=2, autoraise=True)
        print(f"[OK] Browser opened: {target}")
    except Exception as exc:
        try:
            webbrowser.open(target, new=2, autoraise=True)
            print(f"[OK] Browser opened: {target}")
        except Exception:
            print(f"[WARNING] Failed to open browser automatically: {exc}")
            print(f"          Open manually: {target}")


def main() -> None:
    load_root_env()

    education_port = get_env_int("EDUCATION_API_PORT", DEFAULT_EDUCATION_API_PORT)
    maintenance_port = get_env_int("MAINTENANCE_API_PORT", DEFAULT_MAINTENANCE_API_PORT)
    frontend_port = get_env_int("FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    backend_admin_port = get_env_int("BACKEND_ADMIN_PORT", DEFAULT_BACKEND_ADMIN_PORT)

    frontend_base_url = build_service_base_url("FRONTEND_BASE_URL", "FRONTEND_PORT", frontend_port)
    backend_admin_base_url = build_service_base_url("BACKEND_ADMIN_BASE_URL", "BACKEND_ADMIN_PORT", backend_admin_port)

    write_frontend_runtime_config(FRONTEND_CONFIG_PATH)
    generate_frontend_cache()

    print("\n" + "=" * 50)
    print("Knowledge-Gragph-Teaching-System 启动器")
    print("=" * 50)
    print(f"Python: {get_runtime_python()}")
    print("本次只保留当前一个控制台，服务日志写入 .runtime/logs。")
    print("即将启动:")
    print(f"  1. 教育 API ({education_port})")
    print(f"  2. 后台维护 API ({maintenance_port})")
    print(f"  3. 后端知识图谱管理页 ({backend_admin_port})")
    print(f"  4. 前端页面服务 ({frontend_port})")
    print("=" * 50)

    processes: dict[str, subprocess.Popen[bytes]] = {}
    ports = {
        "education": education_port,
        "maintenance": maintenance_port,
        "backend-admin": backend_admin_port,
        "frontend": frontend_port,
    }

    try:
        processes["education"] = start_api_server(
            BACKEND_DIR / "education" / "api_server.py",
            education_port,
            "教育 API",
        )
        processes["maintenance"] = start_api_server(
            BACKEND_DIR / "maintenance" / "api_server.py",
            maintenance_port,
            "后台维护 API",
        )
        processes["backend-admin"] = start_backend_admin_server(backend_admin_port)
        processes["frontend"] = start_frontend_server(frontend_port)
        write_pid_file(processes, ports)

        print("\n" + "=" * 50)
        print("全部服务已启动")
        print("=" * 50)
        print("访问地址:")
        print(f"  - 主界面: {frontend_base_url}/")
        print(f"  - 学生端: {frontend_base_url}/student.html")
        print(f"  - 教师端: {frontend_base_url}/teacher.html")
        print(f"  - 后端知识图谱管理: {backend_admin_base_url}/admin")
        loopback_host = get_loopback_host()
        print(f"  - 教育 API 文档: http://{loopback_host}:{education_port}/docs")
        print(f"  - 维护 API 文档: http://{loopback_host}:{maintenance_port}/docs")
        print("=" * 50)
        print("按 Ctrl+C 停止全部服务。也可以另开一次 PowerShell 运行 .\\stop.ps1。")

        time.sleep(5)
        print("[OK] 启动等待完成。")
        open_frontend_home(frontend_base_url)

        while True:
            time.sleep(2)
            all_running = True
            for name, process in processes.items():
                exit_code = process.poll()
                if exit_code is None:
                    continue

                if exit_code == 0:
                    print(f"[OK] {name} 正常退出 ({exit_code})")
                else:
                    print(f"[WARNING] {name} 异常退出 ({exit_code})，请查看 .runtime/logs")
                all_running = False

            if not all_running:
                break

    except KeyboardInterrupt:
        print("\n用户中断。")
    finally:
        stop_processes(processes)
        clear_pid_file()
        close_logs()
        print("\n" + "=" * 50)
        print("全部服务已停止")
        print("=" * 50)


if __name__ == "__main__":
    main()
