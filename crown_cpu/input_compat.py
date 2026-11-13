FILE_STEM_TO_TEMPLATE_NAME = {
    "CSv1": "Cyber Standard v1",
    "GSv1": "Generic Standard v1",
    "Mv1": "Mature v1",
    "rev1": "st_tooth",
    "SSv1": "Soft Standard v1",
    "Yv1": "Youth v1",
}


def file_name2template_name(file_name):
    stem = file_name.split("_")[0]
    return FILE_STEM_TO_TEMPLATE_NAME[stem]


def merge_missing_fields(base, extra):
    merged = dict(base)
    if not isinstance(extra, dict):
        return merged

    for key, value in extra.items():
        if key not in merged:
            merged[key] = value

    return merged


def load_input_info(event, requests_module):
    if event.get("source_url"):
        response = requests_module.get(event.get("source_url"))
        return response.json()

    return event


def upload_result(target_url, data, requests_module):
    response = requests_module.put(
        target_url,
        json=data,
        headers={"Content-Type": "binary/octet-stream"},
    )
    response.raise_for_status()
    return response
