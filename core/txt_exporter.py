"""
txt_exporter.py
Ekspor kontak dari file VCF ke file TXT berisi daftar nomor.
"""
from core.vcf_parser import parse_vcf_file


def export_vcf_to_txt(vcf_paths: list, output_path: str) -> int:
    """
    Baca semua nomor dari file VCF secara berurutan,
    tulis ke file TXT satu nomor per baris.
    Kembalikan total jumlah nomor.
    """
    all_numbers = []
    for path in vcf_paths:
        contacts = parse_vcf_file(path)
        for c in contacts:
            all_numbers.append(c["tel"])

    with open(output_path, "w", encoding="utf-8") as f:
        for num in all_numbers:
            f.write(num + "\n")

    return len(all_numbers)
