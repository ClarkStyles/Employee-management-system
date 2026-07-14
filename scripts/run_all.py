import os
import sys
import time
import subprocess
import threading

def run_process(name, cmd, cwd):
    print(f"Starting {name}...")
    # Use shell=True for windows to handle venv correctly if needed
    p = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    def log_output():
        for line in p.stdout:
            print(f"[{name}] {line}", end="")
            
    t = threading.Thread(target=log_output, daemon=True)
    t.start()
    return p

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = os.path.join(base_dir, "backend")
    
    print("Starting Redis...")
    redis_path = os.path.join(base_dir, "redis_bin", "redis-server.exe")
    if os.path.exists(redis_path):
        p_redis = run_process("Redis", f'"{redis_path}"', base_dir)
    else:
        print("Local redis-server.exe not found. Proceeding anyway...")
    
    # Download model if missing
    subprocess.run(f'"{sys.executable}" scripts/download_model.py', cwd=base_dir, shell=True)
    
    # Run timeout checker
    p_checker = run_process("TimeoutChecker", f'"{sys.executable}" manage.py run_timeout_checker', backend_dir)
    
    # Run redis subscriber
    p_sub = run_process("Subscriber", f'"{sys.executable}" manage.py run_subscriber', backend_dir)
    
    # Run backend
    p_backend = run_process("Django", "daphne -b 0.0.0.0 -p 8000 backend.asgi:application", backend_dir)
    
    # Note: cv_worker not started automatically so it doesn't try to access webcam if no video file.
    # User can run scripts/simulate_crowd.py instead.
    print("\n" + "="*50)
    print("Services Started!")
    print("Frontend URL: http://localhost:8000/")
    print("To simulate a crowd: python scripts/simulate_crowd.py --zone 2")
    print("To run real CV: python -m cv_worker.main (from root)")
    print("="*50 + "\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        p_backend.terminate()
        p_sub.terminate()
        p_checker.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()
