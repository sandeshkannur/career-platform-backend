import os
import datetime

# ================= CONFIGURATION =================
SNAPSHOT_DIR = "Snapshot"

# Output Filenames (Stored inside SNAPSHOT_DIR)
FILE_TREE = "00_project_structure.txt"
FILE_CODE = "01_backend_code_with_lines.txt"

# 1. Folders to IGNORE (Backend specific)
IGNORE_DIRS = {
    ".git", ".idea", ".vscode", ".DS_Store",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "env", 
    "pgdata", "pgdata_backup", "dist", "build", "coverage", "htmlcov",
    SNAPSHOT_DIR # Important: Ignore the output folder itself
}

# 2. Extensions to INCLUDE (Backend focus)
INCLUDE_EXTENSIONS = {
    ".py", ".sql", ".js", ".html", ".css", 
    ".json", ".yml", ".yaml", ".toml", ".ini", ".env", ".xml",
    ".md", ".txt", ".sh", ".bat", ".ps1", "Dockerfile", ".dockerfile"
}

# 3. Files to IGNORE
IGNORE_FILES = {
    "generate_snapshot.py", "auto_update.py", ".DS_Store", "thumbs.db",
    "alembic_draft.db", "dev.db", "dev.sqlite" # Ignoring local DB files
}

MAX_FILE_SIZE = 500 * 1024  # 500 KB

# ================================================

def get_tree(startpath):
    lines = []
    lines.append(".")
    
    def _walk(current_path, prefix=""):
        try: 
            items = sorted(os.listdir(current_path))
        except: return

        filtered = []
        for item in items:
            if item in IGNORE_FILES: continue
            if os.path.isdir(os.path.join(current_path, item)) and item in IGNORE_DIRS: continue
            filtered.append(item)

        for i, item in enumerate(filtered):
            path = os.path.join(current_path, item)
            is_last = (i == len(filtered) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{item}")
            if os.path.isdir(path):
                ext = "    " if is_last else "│   "
                _walk(path, prefix + ext)

    _walk(startpath)
    return "\n".join(lines)

def write_header(file_handle, title, root_dir):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_handle.write("="*50 + "\n")
    file_handle.write(f"{title}\nRoot: {root_dir}\nGenerated: {ts}\n")
    file_handle.write("="*50 + "\n\n")

def generate_snapshot():
    root_dir = os.getcwd()
    out_dir = os.path.join(root_dir, SNAPSHOT_DIR)
    os.makedirs(out_dir, exist_ok=True)

    path_tree = os.path.join(out_dir, FILE_TREE)
    path_code = os.path.join(out_dir, FILE_CODE)

    print(f"📸 Generating Backend snapshot in: {SNAPSHOT_DIR}/ ...")

    # --- 1. Generate Tree ---
    with open(path_tree, "w", encoding="utf-8") as f:
        write_header(f, "BACKEND PROJECT STRUCTURE", root_dir)
        f.write(get_tree(root_dir))

    # --- 2. Generate Code File WITH LINE NUMBERS ---
    with open(path_code, "w", encoding="utf-8") as f_code:
        write_header(f_code, "COMPLETE BACKEND CODE (WITH LINE NUMBERS)", root_dir)

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
            files.sort()

            for file in files:
                if file in IGNORE_FILES: continue
                _, ext = os.path.splitext(file)
                if file not in INCLUDE_EXTENSIONS and ext not in INCLUDE_EXTENSIONS: continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, root_dir) 
                
                # Size Check
                try:
                    if os.path.getsize(file_path) > MAX_FILE_SIZE:
                        f_code.write(f"\n--- SKIPPED LARGE FILE: {rel_path} ---\n")
                        continue
                except: continue

                # Read Content and Add Line Numbers
                header = f"\n{'='*60}\nFILE: {rel_path}\n{'='*60}\n"
                f_code.write(header)
                try:
                    with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines, 1):
                            # The {i:4d} formats the line number to be 4 characters wide
                            f_code.write(f"{i:4d} | {line}")
                    f_code.write("\n")
                except Exception as e:
                    f_code.write(f"[Error reading file: {e}]\n")

    print("✅ Done! 2 files updated in 'Snapshot' folder.")

if __name__ == "__main__":
    generate_snapshot()

    