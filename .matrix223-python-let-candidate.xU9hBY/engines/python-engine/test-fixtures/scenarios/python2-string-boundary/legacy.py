from __future__ import unicode_literals

import six


def copy_payload(request, source_path, output_path, count, total):
    payload = str(request.data)
    with open(source_path, "rb") as source:
        binary = source.read()
    with open(output_path, "wb") as target:
        target.write(payload)
        target.write(binary)
    print payload
    return count / total
