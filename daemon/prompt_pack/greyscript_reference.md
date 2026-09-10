# GreyScript quick reference (Grey Hack)

GreyScript is a MiniScript-derived language embedded in Grey Hack. It runs on
the game's own interpreter; there is no I/O beyond the game's APIs.

## Grey Hack singleplayer save format (for tooling that touches it)

The world lives in `Grey Hack_Data/GreyHackDB.db` (SQLite, in the game
install dir). `Files` rows are content-addressed (ID = md5 hex of content,
plus refCount); `Computer.FileSystem` is a JSON tree (folder nodes have
`nombre`/`files`/`folders`, file nodes have `nombre` + `ID` into Files).
The game repoints a file's tree node to a new md5 row whenever it rewrites
the file — external tools must resolve IDs from the tree at access time.
Updating a row's Content in place IS seen by a running game (reads don't
re-hash).

## Language core

```
// variables (numbers, strings, lists, maps, null)
name = "world"
count = 3 + 4 * 2

// string
greeting = "hello " + name
line_count = greeting.len            // .len works on strings and lists
parts = "a,b,c".split(",")
letters = "abc"[0]                   // -> "a"

// list
fruits = ["apple", "pear"]
fruits.push("plum")
first = fruits[0]
n = fruits.len

// map  (curly braces; dot access for simple keys)
user = {"name": "mark", "level": 4}
user["level"] = 5
user.level = 5
if user["missing"] == null then print("absent key reads as null")

// control flow
if count > 5 then
	print("big")
else if count > 2 then
	print("medium")
else
	print("small")
end if

for fruit in fruits
	print(fruit)
end for

for i in range(1, 10)
	print(i)
end for

while count > 0
	count = count - 1
end while

// functions: assignment form, closed with end function
add = function(a, b)
	sum = a + b
	return sum
end function

// globals across functions
remember = function(x)
	globals.last = x
end function
```

## Terminal program skeleton

```
// tool.src — run from the in-game terminal
main = function(params)
	if params == null or params.len == 0 then
		print("usage: tool <arg>")
		return null
	end if
	print("got: " + params[0])
	return null
end function

main(params)
```

`params` is a global list of the words after the program name. `print` writes
to the terminal. `wait(seconds)` pauses (max 300 per call); keep waits
bounded.

## File system API

```
comp = get_shell.host_computer

folder = comp.File("/home/guest")     // File object or null

// create a folder: parent path + folder name (NOT one full path)
result = comp.create_folder("/home/guest", "stuff")

// create an empty file: parent path + file name (NOT one full path)
result = comp.touch("/home/guest", "greet.txt")

f = comp.File("/home/guest/greet.txt")
f.set_content("new contents")
print(f.get_content)
print(f.path)                          // full path
print(f.name)                          // file name

files = folder.get_files               // list of File
subfolders = folder.get_folders
f.delete
```

Useful globals: `home_dir` (current user's home path, use bare, no parens),
`parent_path("/a/b/c")` (parent directory of a path), `active_user` (name),
`current_path`, `program_path`.

Running other programs: `get_shell.launch("/path/program", "arg1 arg2")` —
returns 1 on success, 0 on failure, or an error string.

Pausing: `wait(seconds)` — NOT `sleep`. One call may wait at most 300
seconds. `yield` waits one tick.

## Common gotchas

- There is NO `create_file` method and NO `sleep` function — use `touch` and
  `wait`. `touch`/`create_folder` take (parentPath, name), not a full path.
- `range(a, b)` is INCLUSIVE in both directions: `range(1,3)` = [1,2,3] and
  `range(1,0)` = [1,0] (countdown!). One-arg `range(5)` counts DOWN. To join
  CLI words: `params.join(" ")` — never a range loop over params.
- `split()` is REGEX-based: `.` `|` `*` `+` `?` `(` `)` `[` `]` `\` `^` `$`
  in the separator must be escaped; prefer inert delimiters like `;` or `,`.
- Reading a MISSING MAP KEY throws "Key Not Found" — check with
  `map.hasIndex(key)` (returns 1/0) before indexing.
- `indexOf` returns null on miss (not -1); `lastIndexOf` returns -1.
- `replace()` does NOT work on strings (maps/lists only) — use
  `replace_regex` for strings.
- No-argument members are used BARE: `file.get_content`, `folder.get_files`,
  `file.delete`, `file.path`. Parentheses are for calls with arguments:
  `file.set_content("x")`, `comp.touch("/tmp", "a.txt")`.
- String escapes work: `"a\nb"` is 3 chars. `char(10)` is a newline;
  `code(s)` is ord (crashes on empty string).
- `exit("message")` terminates the program — the idiomatic way to print
  usage errors. `wait(s)` pauses 0.01–300s per call.
- `0`, `""`, and `null` are falsy. Community idiom: `if not file then`.
- `params` in terminal programs may be null, empty, or `[""]` — guard all
  three shapes.
- Programs have an execution budget: no infinite loops; poll with `wait(1)`
  and a max wait counter.
- No real networking, no sockets, no HTTP. "Network" APIs are the game's
  simulated ones (verify exact signatures with `man` in-game).

## In-game help

The terminal command `man <name>` shows documentation for programs and
libraries (e.g. `man nmap`). When unsure about an API, tell the user to run
`man` and paste the output back.
