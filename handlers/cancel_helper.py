"""
cancel_helper.py
Batalkan semua proses aktif user — dipanggil dari /start dan /reset.
"""
import asyncio
from handlers.merge import _user_bg_tasks as merge_tasks, _user_locks as merge_locks, _clear_buffers as merge_clear, _user_status_msg as merge_msg
from handlers.vcftotxt import _user_bg_tasks as vcf2txt_tasks, _user_locks as vcf2txt_locks, _clear_buffers as vcf2txt_clear, _user_status_msg as vcf2txt_msg
from handlers.txttovcf import _user_bg_tasks as ttv_tasks, _user_locks as ttv_locks, _clear_buffers as ttv_clear, _user_status_msg as ttv_msg
from handlers.count import _user_bg_tasks as count_tasks, _user_locks as count_locks, clear_user_dir as count_clear, _user_status_msg as count_msg
from handlers.xlsxtotxt import _user_bg_tasks as xlsx_tasks, _user_locks as xlsx_locks, clear_user_dir as xlsx_clear, _user_status_msg as xlsx_msg

async def cancel_all(user_id: int, context):
    """Batalkan semua proses aktif dan bersihkan memori/disk user."""

    # 1. Hapus Status Message (GUI)
    for msg_dict in [merge_msg, vcf2txt_msg, ttv_msg, count_msg, xlsx_msg]:
        msg_id = msg_dict.pop(user_id, None)
        if msg_id:
            try: await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
            except: pass

    # 2. Cancel semua background tasks
    for tasks_dict in [merge_tasks, vcf2txt_tasks, ttv_tasks, count_tasks, xlsx_tasks]:
        tasks = tasks_dict.pop(user_id, set())
        for t in tasks:
            try: t.cancel()
            except: pass

    # 3. Hapus semua buffer disk
    for clear_func in [merge_clear, vcf2txt_clear, ttv_clear, count_clear, xlsx_clear]:
        try: clear_func(user_id)
        except: pass

    # 4. Hapus lock & Clean session
    for locks in [merge_locks, vcf2txt_locks, ttv_locks, count_locks, xlsx_locks]:
        locks.pop(user_id, None)