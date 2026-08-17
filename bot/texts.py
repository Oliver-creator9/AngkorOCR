"""All user-facing copy, in one place so nothing is hardcoded in a handler."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "start": (
            "Send me a photo, a scan, or a PDF and I'll send the text back.\n\n"
            "Use /help to see everything I can do."
        ),
        "help": (
            "/lang — set OCR language(s), e.g. <code>/lang eng+khm</code>\n"
            "/engine — switch between tesseract and vision\n"
            "/settings — see your current settings\n"
            "/search — find text from past scans\n"
            "/quota — check today's usage\n"
            "/privacy — how your data is handled\n"
            "/forgetme — erase your history now\n"
            "/cancel — cancel the current action"
        ),
        "unsupported": "I don't know what to do with that. Send a photo, image file, or PDF.",
        "too_big": "That file is {size} MB — the limit is {limit} MB.",
        "quota_exceeded": "You've used today's quota of {limit} pages. Try again tomorrow.",
        "processing": "Processing{pages}…",
        "no_text": "I couldn't find any text in that.",
        "error": "Something went wrong on my end. Please try again.",
        "rate_limited": "Slow down a little — you're sending updates too fast.",
        "cancelled": "Cancelled.",
        "lang_current": "Current OCR language(s): {langs}\nInstalled: {installed}",
        "lang_set": "OCR language(s) set to {langs}.",
        "lang_invalid": "Not installed on this server: {missing}",
        "engine_current": "Current engine: {engine}",
        "engine_set": "Engine set to {engine}.",
        "engine_unavailable": "The vision engine isn't configured on this server.",
        "settings_summary": "Languages: {langs}\nEngine: {engine}\nTier: {tier}",
        "search_usage": "Usage: /search <text>",
        "search_no_results": "No past scans match “{query}”.",
        "search_results_header": "{count} result(s):",
        "search_result_item": "{date} · {chars} chars\n{snippet}",
        "quota_status": "{used} / {limit} pages used today.",
        "privacy_notice": (
            "Images are processed in memory and never written to disk. Extracted text is kept "
            "for {days} days so /search works, then erased automatically. /forgetme erases it now."
        ),
        "forgetme_done": "Done — your history has been erased.",
        "admin_only": "That command is for admins only.",
        "stats_summary": "Users: {users}\nJobs (24h): {jobs}\nAvg duration (24h): {avg_ms} ms",
        "block_done": "Blocked user {id}.",
        "unblock_done": "Unblocked user {id}.",
        "grant_done": "User {id} is now {tier}.",
        "admin_usage": "Usage: /block <id> · /unblock <id> · /grant <id> premium",
    },
    "km": {
        "start": (
            "ផ្ញើរូបថត ឯកសារស្កេន ឬ PDF មកខ្ញុំ ហើយខ្ញុំនឹងផ្ញើអត្ថបទត្រឡប់មកវិញ។\n\n"
            "ប្រើ /help ដើម្បីមើលអ្វីៗទាំងអស់ដែលខ្ញុំអាចធ្វើបាន។"
        ),
        "help": (
            "/lang — កំណត់ភាសា OCR ឧទាហរណ៍ <code>/lang eng+khm</code>\n"
            "/engine — ប្តូររវាង tesseract និង vision\n"
            "/settings — មើលការកំណត់បច្ចុប្បន្នរបស់អ្នក\n"
            "/search — ស្វែងរកអត្ថបទពីការស្កេនមុនៗ\n"
            "/quota — ពិនិត្យការប្រើប្រាស់ថ្ងៃនេះ\n"
            "/privacy — របៀបគ្រប់គ្រងទិន្នន័យរបស់អ្នក\n"
            "/forgetme — លុបប្រវត្តិរបស់អ្នកឥឡូវនេះ\n"
            "/cancel — បោះបង់សកម្មភាពបច្ចុប្បន្ន"
        ),
        "unsupported": "ខ្ញុំមិនដឹងថាត្រូវធ្វើអ្វីជាមួយវាទេ។ ផ្ញើរូបថត ឯកសាររូបភាព ឬ PDF។",
        "too_big": "ឯកសារនោះមានទំហំ {size} MB — កំណត់អតិបរមាគឺ {limit} MB។",
        "quota_exceeded": "អ្នកបានប្រើកូតាថ្ងៃនេះចំនួន {limit} ទំព័រហើយ។ សូមព្យាយាមម្តងទៀតនៅថ្ងៃស្អែក។",
        "processing": "កំពុងដំណើរការ{pages}…",
        "no_text": "ខ្ញុំរកមិនឃើញអត្ថបទណាមួយក្នុងនោះទេ។",
        "error": "មានបញ្ហាកើតឡើងខាងខ្ញុំ។ សូមព្យាយាមម្តងទៀត។",
        "rate_limited": "សូមថយវេគបន្តិច — អ្នកកំពុងផ្ញើសារលឿនពេក។",
        "cancelled": "បានបោះបង់។",
        "lang_current": "ភាសា OCR បច្ចុប្បន្ន៖ {langs}\nបានដំឡើង៖ {installed}",
        "lang_set": "កំណត់ភាសា OCR ទៅជា {langs} ហើយ។",
        "lang_invalid": "មិនបានដំឡើងនៅលើម៉ាស៊ីនមេនេះទេ៖ {missing}",
        "engine_current": "ម៉ាស៊ីនបច្ចុប្បន្ន៖ {engine}",
        "engine_set": "កំណត់ម៉ាស៊ីនទៅជា {engine} ហើយ។",
        "engine_unavailable": "ម៉ាស៊ីន vision មិនត្រូវបានកំណត់រចនាសម្ព័ន្ធនៅលើម៉ាស៊ីនមេនេះទេ។",
        "settings_summary": "ភាសា៖ {langs}\nម៉ាស៊ីន៖ {engine}\nកម្រិត៖ {tier}",
        "search_usage": "របៀបប្រើ៖ /search <អត្ថបទ>",
        "search_no_results": "គ្មានការស្កេនមុនដែលត្រូវនឹង “{query}” ទេ។",
        "search_results_header": "លទ្ធផល {count} ៖",
        "search_result_item": "{date} · {chars} តួអក្សរ\n{snippet}",
        "quota_status": "បានប្រើ {used} / {limit} ទំព័រថ្ងៃនេះ។",
        "privacy_notice": (
            "រូបភាពត្រូវបានដំណើរការក្នុងសតិ ហើយមិនដែលសរសេរទៅឌីស្កទេ។ អត្ថបទដែលបានស្រង់ចេញត្រូវបានរក្សាទុក "
            "រយៈពេល {days} ថ្ងៃ ដើម្បីឱ្យ /search ដំណើរការ បន្ទាប់មកលុបដោយស្វ័យប្រវត្តិ។ /forgetme លុបវាឥឡូវនេះ។"
        ),
        "forgetme_done": "រួចរាល់ — ប្រវត្តិរបស់អ្នកត្រូវបានលុបហើយ។",
        "admin_only": "ពាក្យបញ្ជានោះសម្រាប់តែអ្នកគ្រប់គ្រងប៉ុណ្ណោះ។",
        "stats_summary": "អ្នកប្រើប្រាស់៖ {users}\nការងារ (24ម៉ោង)៖ {jobs}\nរយៈពេលមធ្យម (24ម៉ោង)៖ {avg_ms} ms",
        "block_done": "បានទប់ស្កាត់អ្នកប្រើប្រាស់ {id}។",
        "unblock_done": "បានដោះទប់ស្កាត់អ្នកប្រើប្រាស់ {id}។",
        "grant_done": "អ្នកប្រើប្រាស់ {id} ឥឡូវនេះជា {tier} ហើយ។",
        "admin_usage": "របៀបប្រើ៖ /block <id> · /unblock <id> · /grant <id> premium",
    },
}


def t(key: str, lang: str, **kwargs: object) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key, STRINGS["en"].get(key, key))
    return template.format(**kwargs) if kwargs else template
