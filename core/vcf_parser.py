"""
vcf_parser.py
Baca dan tulis file VCF. Tidak mengubah format nomor,
hanya menambahkan + di depan jika belum ada.
"""

def add_plus(number: str) -> str:
    import re
    number = number.strip()
    if not number:
        return number

    # Sudah ada + di depan, bersihkan karakter kotor sisanya
    if number.startswith("+"):
        return "+" + re.sub(r"[\s\-\.\(\),]", "", number[1:])

    # Bersihkan semua karakter kotor
    cleaned = re.sub(r"[\s\-\.\(\),]", "", number)

    # Indonesia: 08xxx → +628xxx
    if cleaned.startswith("08"):
        return "+62" + cleaned[1:]

    # Sudah format 628xxx
    if cleaned.startswith("628"):
        return "+" + cleaned

    # Format lain tambah + saja
    return "+" + cleaned


def parse_vcf(content: str) -> list:
    """
    Baca isi VCF string, kembalikan list of dict:
    [{"name": "...", "tel": "..."}, ...]
    Urutan sesuai urutan di file.
    """
    contacts = []
    current = {}
    for line in content.splitlines():
        line = line.strip()
        if line.upper() == "BEGIN:VCARD":
            current = {}
        elif line.upper().startswith("FN:"):
            current["name"] = line[3:]
        elif line.upper().startswith("TEL"):
            # Ambil nilai setelah tanda :
            if ":" in line:
                tel = line.split(":", 1)[1].strip()
                current["tel"] = add_plus(tel)
        elif line.upper() == "END:VCARD":
            if "tel" in current:
                if "name" not in current:
                    current["name"] = current["tel"]
                contacts.append(current)
            current = {}
    return contacts


def parse_vcf_file(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return parse_vcf(content)


def contacts_to_vcf(contacts: list) -> str:
    """
    Ubah list of dict ke string VCF.
    contacts = [{"name": "FEE1", "tel": "+628xxx"}, ...]
    """
    lines = []
    for c in contacts:
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        lines.append(f"FN:{c['name']}")
        lines.append(f"TEL;TYPE=CELL:{c['tel']}")
        lines.append("END:VCARD")
    return "\n".join(lines) + "\n"


def write_vcf(filepath: str, contacts: list):
    content = contacts_to_vcf(contacts)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
