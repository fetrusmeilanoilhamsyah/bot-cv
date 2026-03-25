"""
vcf_parser.py
Baca dan tulis file VCF super cepat. Kecepatan ini untuk menghindari GIL block 
pada event loop Telegram.
"""
import re

# Pre-compile regex for maximum performance
_CLEAN_RE = re.compile(r"[\s\-\.\(\),]")

def add_plus(number: str) -> str:
    if not number:
        return ""
    
    number = number.strip()
    if not number:
        return ""

    if number.startswith("+"):
        return "+" + _CLEAN_RE.sub("", number[1:])

    cleaned = _CLEAN_RE.sub("", number)

    if cleaned.startswith("08"):
        return "+62" + cleaned[1:]
    if cleaned.startswith("628"):
        return "+" + cleaned
    return "+" + cleaned


def parse_vcf_lines(lines_iterable) -> list:
    """
    Parser sangat efisien memori. Menerima lazy iterable (misal dari objek file).
    Mencegah string split() berukuran GB yang menahan GIL main thread.
    """
    contacts = []
    current_name = None
    current_tel = None
    
    for line in lines_iterable:
        line = line.strip()
        if not line:
            continue
            
        upper_line = line.upper()
        if upper_line == "BEGIN:VCARD":
            current_name = None
            current_tel = None
        elif upper_line.startswith("FN:"):
            current_name = line[3:]
        elif upper_line.startswith("TEL"):
            if ":" in line:
                tel = line.split(":", 1)[1].strip()
                current_tel = add_plus(tel)
        elif upper_line == "END:VCARD":
            if current_tel:
                if not current_name:
                    current_name = current_tel
                contacts.append({"name": current_name, "tel": current_tel})
            current_name = None
            current_tel = None
            
    return contacts


def parse_vcf(content: str) -> list:
    """Tinggal untuk kapabilitas backwards, panggil the optimized one."""
    return parse_vcf_lines(content.splitlines())


def parse_vcf_file(filepath: str) -> list:
    """Best performant file-to-list."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return parse_vcf_lines(f)


def contacts_to_vcf(contacts: list) -> str:
    """
    Super cepat mengubah ke list of string (C-optimized join).
    """
    lines = []
    for c in contacts:
        lines.append(f"BEGIN:VCARD\nVERSION:3.0\nFN:{c['name']}\nTEL;TYPE=CELL:{c['tel']}\nEND:VCARD")
    return "\n".join(lines) + "\n"

def write_vcf(filepath: str, contacts: list):
    """Tulis VCF langsung ke file_path."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(contacts_to_vcf(contacts))
