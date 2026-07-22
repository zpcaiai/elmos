package io.elmos.semantic;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import static io.elmos.semantic.PspModels.SourceRange;

/** UTF-8 byte/line mapping and a non-evaluating lossless token/trivia fallback. */
final class SourceText {
    record Span(String kind, String textHash, int startChar, int endChar, boolean comment, String commentCategory) {}
    private final String fileId; private final byte[] bytes; private final String text; private final int[] byteOffsets; private final int[] lineStarts;

    private SourceText(String fileId, byte[] bytes, String text) {
        this.fileId = fileId; this.bytes = bytes.clone(); this.text = text; this.byteOffsets = byteOffsets(text); this.lineStarts = lineStarts(text);
    }
    static SourceText utf8(String fileId, byte[] raw) {
        int offset = raw.length >= 3 && (raw[0] & 0xff) == 0xef && (raw[1] & 0xff) == 0xbb && (raw[2] & 0xff) == 0xbf ? 3 : 0;
        try {
            String text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(raw, offset, raw.length - offset)).toString();
            byte[] content = offset == 0 ? raw : java.util.Arrays.copyOfRange(raw, offset, raw.length);
            return new SourceText(fileId, content, text);
        } catch (CharacterCodingException error) { throw new IllegalArgumentException("SOURCE_ENCODING_NOT_UTF8", error); }
    }
    String text() { return text; }
    long byteLength() { return bytes.length; }
    String lineEnding() { return text.contains("\r\n") ? text.replace("\r\n", "").contains("\n") ? "MIXED" : "CRLF" : "LF"; }
    SourceRange range(int startChar, int endChar) {
        int start = Math.max(0, Math.min(startChar, text.length())), end = Math.max(start, Math.min(endChar, text.length()));
        int startLineIndex = lineIndex(start), endLineIndex = lineIndex(end);
        return new SourceRange(fileId, byteOffsets[start], byteOffsets[end], startLineIndex + 1, start - lineStarts[startLineIndex],
                endLineIndex + 1, end - lineStarts[endLineIndex]);
    }
    List<Span> lex(String language) {
        List<Span> spans = new ArrayList<>(); int i = 0; boolean python = language.equals("python");
        while (i < text.length()) {
            char c = text.charAt(i); int start = i;
            if (Character.isWhitespace(c)) { while (i < text.length() && Character.isWhitespace(text.charAt(i))) i++; spans.add(span("whitespace", start, i, false, null)); continue; }
            if (!python && c == '/' && i + 1 < text.length() && text.charAt(i + 1) == '/') { i += 2; while (i < text.length() && text.charAt(i) != '\n') i++; spans.add(span("comment", start, i, true, category(start, i))); continue; }
            if (!python && c == '/' && i + 1 < text.length() && text.charAt(i + 1) == '*') { i += 2; while (i + 1 < text.length() && !(text.charAt(i) == '*' && text.charAt(i + 1) == '/')) i++; i = Math.min(text.length(), i + 2); spans.add(span("comment", start, i, true, category(start, i))); continue; }
            if (python && c == '#') { i++; while (i < text.length() && text.charAt(i) != '\n') i++; spans.add(span("comment", start, i, true, category(start, i))); continue; }
            if (c == '"' || c == '\'') { char quote = c; boolean triple = python && i + 2 < text.length() && text.charAt(i + 1) == quote && text.charAt(i + 2) == quote; i += triple ? 3 : 1; while (i < text.length()) { if (!triple && text.charAt(i) == '\\') { i = Math.min(text.length(), i + 2); continue; } if (triple && i + 2 < text.length() && text.charAt(i) == quote && text.charAt(i + 1) == quote && text.charAt(i + 2) == quote) { i += 3; break; } if (!triple && text.charAt(i) == quote) { i++; break; } i++; } spans.add(span("string", start, i, false, null)); continue; }
            if (Character.isJavaIdentifierStart(c) || c == '$') { i++; while (i < text.length() && (Character.isJavaIdentifierPart(text.charAt(i)) || text.charAt(i) == '$')) i++; spans.add(span("identifier", start, i, false, null)); continue; }
            if (Character.isDigit(c)) { i++; while (i < text.length() && (Character.isLetterOrDigit(text.charAt(i)) || "._".indexOf(text.charAt(i)) >= 0)) i++; spans.add(span("number", start, i, false, null)); continue; }
            i++; if (i < text.length() && "=<>!&|+-*?:".indexOf(c) >= 0 && text.charAt(i) == '=') i++;
            spans.add(span("punctuation", start, i, false, null));
        }
        return spans;
    }
    private Span span(String kind, int start, int end, boolean comment, String category) { return new Span(kind, SemanticIds.hashText(text.substring(start, end)), start, end, comment, category); }
    private String category(int start, int end) { String value = text.substring(start, end).toLowerCase(Locale.ROOT); if (start < 512 && value.contains("license")) return "license-header"; if (value.contains("formatter:") || value.contains("fmt:")) return "formatter-control"; if (value.startsWith("///") || value.startsWith("/**") || value.startsWith("##")) return "documentation"; if (value.contains("type:")) return "type-comment"; return "inline"; }
    private int lineIndex(int charOffset) { int low = 0, high = lineStarts.length - 1; while (low <= high) { int mid = (low + high) >>> 1; if (lineStarts[mid] <= charOffset) low = mid + 1; else high = mid - 1; } return Math.max(0, high); }
    private static int[] lineStarts(String text) { List<Integer> starts = new ArrayList<>(); starts.add(0); for (int i = 0; i < text.length(); i++) if (text.charAt(i) == '\n') starts.add(i + 1); return starts.stream().mapToInt(Integer::intValue).toArray(); }
    private static int[] byteOffsets(String text) { int[] result = new int[text.length() + 1]; int bytes = 0; for (int i = 0; i < text.length();) { int codePoint = text.codePointAt(i), chars = Character.charCount(codePoint), length = codePoint <= 0x7f ? 1 : codePoint <= 0x7ff ? 2 : codePoint <= 0xffff ? 3 : 4; result[i] = bytes; if (chars == 2) result[i + 1] = bytes; bytes += length; i += chars; result[i] = bytes; } return result; }
}
