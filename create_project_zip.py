"""
Create Project Zip File for TradeSense Pro
Excludes __pycache__, .git, and temporary files.
"""
import os
import zipfile

def make_zip(source_dir, output_zip_path):
    exclude_dirs = {'__pycache__', '.git', '.vscode', '.idea', 'venv', '.env_backup'}
    exclude_extensions = {'.pyc', '.pyo'}
    exclude_files = {os.path.basename(output_zip_path)}

    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file in exclude_files:
                    continue
                if any(file.endswith(ext) for ext in exclude_extensions):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                zipf.write(full_path, rel_path)
                
    file_size_mb = os.path.getsize(output_zip_path) / (1024 * 1024)
    print(f"[SUCCESS] Created {output_zip_path} ({file_size_mb:.2f} MB)")

if __name__ == '__main__':
    src = r"c:\Users\DELL\Desktop\abdullah"
    dest = r"c:\Users\DELL\Desktop\abdullah\TradeSense_Pro_Complete_System.zip"
    make_zip(src, dest)
