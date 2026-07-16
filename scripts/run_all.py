import os
import sys
import time
import socket
import subprocess
import webbrowser

def run_process(name, cmd, cwd):
    print(f"Starting {name}...", flush=True)
    return subprocess.Popen(cmd, cwd=cwd, shell=True)

def kill_port(port):
    """Kill whichever process is occupying the given TCP port (Windows only)."""
    try:
        # Use netstat to find the PID using the port
        result = subprocess.run(
            f'netstat -ano | findstr ":{port} " | findstr "LISTENING"',
            shell=True, capture_output=True, text=True
        )
        pids = set()
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != '0':
                    pids.add(pid)
        for pid in pids:
            subprocess.run(f'taskkill /PID {pid} /F', shell=True,
                           capture_output=True)
        if pids:
            print(f"  Freed port {port} (killed PIDs: {', '.join(pids)})", flush=True)
            time.sleep(0.5)  # Brief pause for OS to release the port
    except Exception as e:
        print(f"  Warning: could not free port {port}: {e}", flush=True)

def is_port_open(host, port):
    """Return True if something is already listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(base_dir, "backend")
    p_redis = None

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_path = os.path.join(base_dir, "redis_bin", "redis-server.exe")
    if is_port_open("127.0.0.1", 6379):
        print("Redis already running on port 6379 — skipping launch.", flush=True)
    elif os.path.exists(redis_path):
        p_redis = run_process("Redis", f'"{redis_path}"', base_dir)
        time.sleep(1)  # Give Redis a moment to bind
    else:
        print("Local redis-server.exe not found. Proceeding anyway...", flush=True)

    # ── Model download (skip if present) ───────────────────────────────────
    subprocess.run(
        f'"{sys.executable}" scripts/download_model.py',
        cwd=base_dir, shell=True
    )

    # ── Background services ────────────────────────────────────────────────
    p_checker = run_process(
        "TimeoutChecker",
        f'"{sys.executable}" manage.py run_timeout_checker',
        backend_dir,
    )
    p_sub = run_process(
        "Subscriber",
        f'"{sys.executable}" manage.py run_subscriber',
        backend_dir,
    )

    # ── Django/Daphne backend ──────────────────────────────────────────────
    # Kill any stale process on port 8000 so restarts always succeed
    print("Freeing port 8000...", flush=True)
    kill_port(8000)
    p_backend = run_process(
        "Django",
        f'"{sys.executable}" -m daphne -b 0.0.0.0 -p 8000 backend.asgi:application',
        backend_dir,
    )

    # ── CV Worker (reads video sources + zone IDs from the database) ───────
    p_cv = run_process(
        "CV Worker",
        f'"{sys.executable}" -m cv_worker.main',
        base_dir,
    )

    time.sleep(2)
    url = "http://localhost:8000/"
    print("\n" + "=" * 50, flush=True)
    print("All Services Started!", flush=True)
    print(f"  Frontend : {url}", flush=True)
    print(f"  CV Worker: started (reads zone video sources from DB)", flush=True)
    print("  Simulate : python scripts/simulate_crowd.py --zone 2", flush=True)
    print("=" * 50 + "\n", flush=True)

    try:
        webbrowser.open(url)
    except Exception:
        print(f"Open {url} in your browser manually.", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down all services...", flush=True)
        for p in (p_cv, p_backend, p_sub, p_checker):
            try:
                p.terminate()
            except Exception:
                pass
        if p_redis:
            try:
                p_redis.terminate()
            except Exception:
                pass
        sys.exit(0)

if __name__ == "__main__":
    main()
