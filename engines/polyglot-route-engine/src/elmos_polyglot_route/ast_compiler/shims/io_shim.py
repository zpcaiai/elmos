"""I/O, File System, Logging, and HTTP standard library shim across 11 enterprise languages."""

from __future__ import annotations

def log_info(lang: str, msg_expr: str) -> str:
    l = lang.lower().strip()
    if l in ("csharp", "cs"):
        return f"Console.WriteLine({msg_expr});"
    elif l == "java":
        return f"System.out.println({msg_expr});"
    elif l in ("python", "py"):
        return f"print({msg_expr})"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"console.log({msg_expr});"
    elif l in ("go", "golang"):
        return f"fmt.Println({msg_expr})"
    elif l in ("rust", "rs"):
        return f"println!(\"{{}}\", {msg_expr});"
    elif l in ("kotlin", "kt"):
        return f"println({msg_expr})"
    elif l == "php":
        return f"echo {msg_expr} . PHP_EOL;"
    elif l in ("cpp", "c++"):
        return f"std::cout << {msg_expr} << std::endl;"
    elif l == "swift":
        return f"print({msg_expr})"
    elif l in ("objc", "objective-c"):
        return f"NSLog(@\"%@\", {msg_expr});"
    return f"print({msg_expr})"

def log_error(lang: str, msg_expr: str) -> str:
    l = lang.lower().strip()
    if l in ("csharp", "cs"):
        return f"Console.Error.WriteLine({msg_expr});"
    elif l == "java":
        return f"System.err.println({msg_expr});"
    elif l in ("python", "py"):
        return f"sys.stderr.write(str({msg_expr}) + '\\n')"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"console.error({msg_expr});"
    elif l in ("go", "golang"):
        return f"fmt.Fprintln(os.Stderr, {msg_expr})"
    elif l in ("rust", "rs"):
        return f"eprintln!(\"{{}}\", {msg_expr});"
    elif l in ("kotlin", "kt"):
        return f"System.err.println({msg_expr})"
    elif l == "php":
        return f"fwrite(STDERR, {msg_expr} . PHP_EOL);"
    elif l in ("cpp", "c++"):
        return f"std::cerr << {msg_expr} << std::endl;"
    elif l == "swift":
        return f"fputs(\"\\({msg_expr})\\n\", stderr)"
    elif l in ("objc", "objective-c"):
        return f"NSLog(@\"[ERROR] %@\", {msg_expr});"
    return f"print({msg_expr})"

def file_read_text(path_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ("java", "kotlin"):
        return f"java.nio.file.Files.readString(java.nio.file.Path.of({path_expr}))"
    elif l in ("csharp", "cs"):
        return f"System.IO.File.ReadAllText({path_expr})"
    elif l in ("python", "py"):
        return f"pathlib.Path({path_expr}).read_text(encoding='utf-8')"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"fs.readFileSync({path_expr}, 'utf-8')"
    elif l in ("go", "golang"):
        return f"os.ReadFile({path_expr})"
    elif l in ("rust", "rs"):
        return f"std::fs::read_to_string({path_expr})?"
    elif l == "php":
        return f"file_get_contents({path_expr})"
    elif l in ("cpp", "c++"):
        return f"(std::stringstream() << std::ifstream({path_expr}).rdbuf()).str()"
    elif l == "swift":
        return f"try String(contentsOfFile: {path_expr}, encoding: .utf8)"
    elif l in ("objc", "objective-c"):
        return f"[NSString stringWithContentsOfFile:{path_expr} encoding:NSUTF8StringEncoding error:nil]"
    return f"open({path_expr}).read()"

def file_write_text(path_expr: str, content_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ("java", "kotlin"):
        return f"java.nio.file.Files.writeString(java.nio.file.Path.of({path_expr}), {content_expr})"
    elif l in ("csharp", "cs"):
        return f"System.IO.File.WriteAllText({path_expr}, {content_expr})"
    elif l in ("python", "py"):
        return f"pathlib.Path({path_expr}).write_text({content_expr}, encoding='utf-8')"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"fs.writeFileSync({path_expr}, {content_expr}, 'utf-8')"
    elif l in ("go", "golang"):
        return f"os.WriteFile({path_expr}, []byte({content_expr}), 0644)"
    elif l in ("rust", "rs"):
        return f"std::fs::write({path_expr}, {content_expr})?"
    elif l == "php":
        return f"file_put_contents({path_expr}, {content_expr})"
    elif l in ("cpp", "c++"):
        return f"(std::ofstream({path_expr}) << {content_expr}).close()"
    elif l == "swift":
        return f"try {content_expr}.write(toFile: {path_expr}, atomically: true, encoding: .utf8)"
    elif l in ("objc", "objective-c"):
        return f"[{content_expr} writeToFile:{path_expr} atomically:YES encoding:NSUTF8StringEncoding error:nil]"
    return f"open({path_expr}, 'w').write({content_expr})"

def file_exists(path_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ("java", "kotlin"):
        return f"java.nio.file.Files.exists(java.nio.file.Path.of({path_expr}))"
    elif l in ("csharp", "cs"):
        return f"System.IO.File.Exists({path_expr})"
    elif l in ("python", "py"):
        return f"pathlib.Path({path_expr}).exists()"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"fs.existsSync({path_expr})"
    elif l in ("go", "golang"):
        return f"_, err := os.Stat({path_expr}); err == nil"
    elif l in ("rust", "rs"):
        return f"std::path::Path::new({path_expr}).exists()"
    elif l == "php":
        return f"file_exists({path_expr})"
    elif l in ("cpp", "c++"):
        return f"std::filesystem::exists({path_expr})"
    elif l == "swift":
        return f"FileManager.default.fileExists(atPath: {path_expr})"
    elif l in ("objc", "objective-c"):
        return f"[[NSFileManager defaultManager] fileExistsAtPath:{path_expr}]"
    return f"os.path.exists({path_expr})"

def path_combine(p1: str, p2: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ("java", "kotlin"):
        return f"java.nio.file.Path.of({p1}, {p2}).toString()"
    elif l in ("csharp", "cs"):
        return f"System.IO.Path.Combine({p1}, {p2})"
    elif l in ("python", "py"):
        return f"str(pathlib.Path({p1}) / {p2})"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"path.join({p1}, {p2})"
    elif l in ("go", "golang"):
        return f"filepath.Join({p1}, {p2})"
    elif l in ("rust", "rs"):
        return f"std::path::Path::new({p1}).join({p2}).to_string_lossy().into_owned()"
    elif l == "php":
        return f"{p1} . DIRECTORY_SEPARATOR . {p2}"
    elif l in ("cpp", "c++"):
        return f"(std::filesystem::path({p1}) / {p2}).string()"
    elif l == "swift":
        return f"URL(fileURLWithPath: {p1}).appendingPathComponent({p2}).path"
    elif l in ("objc", "objective-c"):
        return f"[{p1} stringByAppendingPathComponent:{p2}]"
    return f"os.path.join({p1}, {p2})"

def http_get(url_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ("java", "kotlin"):
        return f"java.net.http.HttpClient.newHttpClient().send(java.net.http.HttpRequest.newBuilder(java.net.URI.create({url_expr})).build(), java.net.http.HttpResponse.BodyHandlers.ofString()).body()"
    elif l in ("csharp", "cs"):
        return f"await new System.Net.Http.HttpClient().GetStringAsync({url_expr})"
    elif l in ("python", "py"):
        return f"requests.get({url_expr}).text"
    elif l in ("typescript", "ts", "javascript", "js"):
        return f"await (await fetch({url_expr})).text()"
    elif l in ("go", "golang"):
        return f"http.Get({url_expr})"
    elif l in ("rust", "rs"):
        return f"reqwest::get({url_expr}).await?.text().await?"
    elif l == "php":
        return f"file_get_contents({url_expr})"
    elif l == "swift":
        return f"try await URLSession.shared.data(from: URL(string: {url_expr})!).0"
    return f"requests.get({url_expr}).text"

