This is a check that you can propose what was learned from a correction, not real work. Read the correction in the request
and answer with one JSON object and nothing else:

{"summary": "<one plain sentence>", "topic": "<three to six words>", "ops": [{"op": "lesson.add", "text": "<the general case>", "guard": "<the check>"}]}

The one "lesson.add" states the general case the correction teaches, in one plain sentence, as "text", and the check
that stops a repeat, in plain words, as "guard". Use only the fields its entry in the op reference lists, and leave
out any you can't fill.
