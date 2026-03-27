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
