"""
vcf_builder.py
Buat file VCF dari file TXT berisi daftar nomor telepon.
Urutan nomor mengikuti urutan file TXT yang diberikan, line by line.
Tidak ada nomor acak atau double dalam satu output file.
"""
import os
from core.vcf_parser import add_plus, write_vcf


def read_numbers_from_txt(filepath: str) -> list:
    """Baca semua nomor dari satu file TXT, satu nomor per baris."""
    numbers = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            num = line.strip()
            if num:
                numbers.append(add_plus(num))
    return numbers


def read_all_numbers(txt_paths: list) -> list:
    """
    Baca semua nomor dari semua file TXT secara berurutan.
    Urutan mengikuti urutan file yang diberikan.
    """
    all_numbers = []
    for path in txt_paths:
        all_numbers.extend(read_numbers_from_txt(path))
    return all_numbers


def build_vcf_files(
    txt_paths: list,
    output_dir: str,
    contact_name: str,
    file_name: str,
    per_file: int
) -> tuple:
    """
    Buat file VCF dari daftar file TXT.

    - contact_name : nama kontak dasar, misal "FEE"
    - file_name    : nama file dasar, misal "AYAM GORENG"
    - per_file     : jumlah kontak per file

    Kembalikan (output_files, total_contacts, file_labels)
    - output_files : list path file VCF yang dibuat, berurutan
    - total_contacts: total nomor
    - file_labels  : list nama file tanpa ekstensi untuk ditampilkan ke user
    """
    all_numbers = read_all_numbers(txt_paths)
    total = len(all_numbers)

    output_files = []
    file_labels = []
    contact_counter = 1
    file_counter = 1

    for i in range(0, total, per_file):
        chunk_numbers = all_numbers[i:i + per_file]
        contacts = []
        for num in chunk_numbers:
            contacts.append({
                "name": f"{contact_name}{contact_counter}",
                "tel": num
            })
            contact_counter += 1

        label = f"{file_name} {file_counter}"
        filename = f"{label}.vcf"
        out_path = os.path.join(output_dir, filename)
        write_vcf(out_path, contacts)
        output_files.append(out_path)
        file_labels.append(label)
        file_counter += 1

    return output_files, total, file_labels
