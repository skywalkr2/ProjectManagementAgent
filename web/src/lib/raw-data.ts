// Raw data on screen (design 7.0): a title or a line never shows a data structure. This is the same rule the server applies
// to the text it writes (`api/screen_text.py`): a brace or bracket opening on a quote, a brace or a bracket, a flow mapping
// with a space after its colon, or a double-quoted key. A placeholder such as {name} or {n:02}, a quoted sentence and a
// heading that ends in a colon are not data.
const RAW_DATA = /[{[]\s*["'{[]|\{\s*[A-Za-z_][\w-]*\s*:\s+\S|"\w[\w .-]{0,40}"\s*:/;

/** Whether the text shows a raw data structure. */
export const holdsRawData = (text: string): boolean => RAW_DATA.test(text);
