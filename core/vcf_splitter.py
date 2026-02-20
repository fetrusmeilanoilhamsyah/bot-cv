"""
vcf_splitter.py
Pecah satu file VCF menjadi banyak file berisi N kontak per file.
Penamaan: PECAHAN1.vcf, PECAHAN2.vcf, ...
"""
import os
from core.vcf_parser import parse_vcf_file, write_vcf


def split_vcf(input_path: str, output_dir: str, per_file: int) -> list:
    """
    Pecah file VCF.
    Kembalikan list path file hasil pecahan, berurutan.
    """
    contacts = parse_vcf_file(input_path)
    output_files = []
    total = len(contacts)
    chunk_num = 1

    for i in range(0, total, per_file):
        chunk = contacts[i:i + per_file]
        filename = f"PECAHAN{chunk_num}.vcf"
        out_path = os.path.join(output_dir, filename)
        write_vcf(out_path, chunk)
        output_files.append(out_path)
        chunk_num += 1

    return output_files
