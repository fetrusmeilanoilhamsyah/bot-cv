"""
admin_navy_builder.py
Buat file VCF berisi kontak ADMIN dan NAVY.
"""
import os
from core.vcf_parser import add_plus, write_vcf


def build_admin_navy_vcf(
    admin_numbers: list,
    navy_numbers: list,
    admin_name: str,
    navy_name: str,
    file_name: str,
    output_dir: str
) -> str:
    """
    Buat satu file VCF berisi kontak ADMIN lalu NAVY.
    Kembalikan path file output.
    """
    contacts = []

    for i, num in enumerate(admin_numbers, start=1):
        contacts.append({
            "name": f"{admin_name}{i}" if len(admin_numbers) > 1 else admin_name,
            "tel": add_plus(num.strip())
        })

    for i, num in enumerate(navy_numbers, start=1):
        contacts.append({
            "name": f"{navy_name}{i}" if len(navy_numbers) > 1 else navy_name,
            "tel": add_plus(num.strip())
        })

    filename = f"{file_name}.vcf"
    out_path = os.path.join(output_dir, filename)
    write_vcf(out_path, contacts)
    return out_path
