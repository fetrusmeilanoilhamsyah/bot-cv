"""
session.py
Kelola folder sementara per user di tmp/sessions/{user_id}/
"""
import os
import shutil
import stat
from config import TMP_DIR


def get_user_dir(user_id: int) -> str:
    path = os.path.join(TMP_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _force_remove(func, path, exc_info):
    """
    Handler khusus Windows: kalau file readonly atau masih terkunci,
    paksa ubah permission dulu baru hapus.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def clear_user_dir(user_id: int):
    """
    Hapus semua file sesi user.
    Aman di Windows walau ada file yang masih terbuka.
    """
    path = os.path.join(TMP_DIR, str(user_id))
    if os.path.exists(path):
        # Hapus file satu per satu dulu biar aman
        for root, dirs, files in os.walk(path):
            for file in files:
                try:
                    filepath = os.path.join(root, file)
                    os.chmod(filepath, stat.S_IWRITE)
                    os.unlink(filepath)
                except Exception:
                    pass
        # Hapus folder
        try:
            shutil.rmtree(path, onexc=_force_remove)
        except Exception:
            pass
    os.makedirs(path, exist_ok=True)


def clear_all_sessions():
    """
    Hapus semua folder sesi semua user.
    Dipakai saat /resetdatabase.
    """
    if os.path.exists(TMP_DIR):
        for folder in os.listdir(TMP_DIR):
            folder_path = os.path.join(TMP_DIR, folder)
            if os.path.isdir(folder_path):
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        try:
                            filepath = os.path.join(root, file)
                            os.chmod(filepath, stat.S_IWRITE)
                            os.unlink(filepath)
                        except Exception:
                            pass
                try:
                    shutil.rmtree(folder_path, onexc=_force_remove)
                except Exception:
                    pass
    os.makedirs(TMP_DIR, exist_ok=True)


def get_session_size(user_id: int) -> int:
    """
    Hitung total ukuran file sesi user dalam bytes.
    Berguna untuk pantau user yang upload file terlalu besar.
    """
    path = os.path.join(TMP_DIR, str(user_id))
    total = 0
    if os.path.exists(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                try:
                    total += os.path.getsize(os.path.join(root, file))
                except Exception:
                    pass
    return total