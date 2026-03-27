import re

def sanitize_filename(filename: str) -> str:
    r"""
    Menghapus karakter yang tidak diperbolehkan dalam nama file:
    \ / : * ? " < > |
    Serta membatasi panjang nama file.
    """
    if not filename:
        return "output"
        
    # Hapus karakter ilegal
    filename = re.sub(r'[\\/:*?"<>|]', '', filename)
    
    # Trim whitespace
    filename = filename.strip()
    
    # Jika jadi kosong setelah dibersihkan
    if not filename:
        return "output"
        
    # Batasi panjang (maks 100 karakter)
    return filename[:100]

def get_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Mengembalikan progress bar visual: [████░░░░░░] 40%"""
    if total <= 0: return " [░░░░░░░░░░] 0%"
    filled = int(length * current // total)
    bar = "█" * filled + "░" * (length - filled)
    pct = int(current / total * 100)
    return f" [{bar}] {pct}%"
