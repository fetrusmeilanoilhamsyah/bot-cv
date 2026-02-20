"""
vcf_merger.py
Gabungkan banyak file VCF menjadi satu.
Urutan kontak mengikuti urutan file yang diberikan.
"""
from core.vcf_parser import parse_vcf_file, write_vcf


def merge_vcf_files(file_paths: list, output_path: str) -> int:
    """
    Gabungkan semua file VCF dari file_paths ke output_path.
    Kembalikan total jumlah kontak.
    """
    all_contacts = []
    for fp in file_paths:
        contacts = parse_vcf_file(fp)
        all_contacts.extend(contacts)
    write_vcf(output_path, all_contacts)
    return len(all_contacts)
