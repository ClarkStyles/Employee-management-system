import os
import sys
import time
import subprocess
import webbrowser

def run_process(name, cmd, cwd):
    print(f"Starting {name}...", flush=True)
    return subprocess.Popen(cmd, cwd=cwd, shell=True)

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(base_dir, "backend")
    p_redis = None
    
    print("Starting Redis...", flush=True)
    redis_path = os.path.join(base_dir, "redis_bin", "redis-server.exe")
    if os.path.exists(redis_path):
        p_redis = run_process("Redis", f'"{redis_path}"', base_dir)
    else:
        print("Local redis-server.exe not found. Proceeding anyway...", flush=True)
    
    # Download model if missing
    subprocess.run(f'"{sys.executable}" scripts/download_model.py', cwd=base_dir, shell=True)
    
    # Run timeout checker
    p_checker = run_process("TimeoutChecker", f'"{sys.executable}" manage.py run_timeout_checker', backend_dir)
    
    # Run redis subscriber
    p_sub = run_process("Subscriber", f'"{sys.executable}" manage.py run_subscriber', backend_dir)
    
    # Run backend (use venv python so dependencies resolve correctly)
    p_backend = run_process(
        "Django",
        f'"{sys.executable}" -m daphne -b 0.0.0.0 -p 8000 backend.asgi:application',
        backend_dir,
    )
    
    # Note: cv_worker not started automatically so it doesn't try to access webcam if no video file.
    # User can run scripts/simulate_crowd.py instead.
    time.sleep(2)
    url = "http://localhost:8000/"
    print("\n" + "="*50, flush=True)
    print("Services Started!", flush=True)
    print(f"Frontend URL: {url}", flush=True)
    print("To simulate a crowd: python scripts/simulate_crowd.py --zone 2", flush=True)
    print("To run real CV: python -m cv_worker.main (from root)", flush=True)
    print("="*50 + "\n", flush=True)
    webbrowser.open(url)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        p_backend.terminate()
        p_sub.terminate()
        p_checker.terminate()
        if p_redis:
            p_redis.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()
