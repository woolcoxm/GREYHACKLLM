# GreyScript quick reference (Grey Hack)

GreyScript is a MiniScript-derived language embedded in Grey Hack. It runs on
the game's own interpreter; there is no I/O beyond the game's APIs.

The sections below are the verified essentials. A COMPLETE generated API
reference (every type, method, return value and official usage example for
the whole game API) is appended to this file and searchable with the api_doc
tool: call api_doc("router"), api_doc("net_use"), api_doc("string split")
before using any API not covered below. If an API is not in this reference
and api_doc cannot find it, it does not exist — do not invent it.

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
user = {"name": "guest", "level": 4}
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

## Networking API (VERIFIED — never invent network APIs)

There is NO `NetUtil`, NO `scan()`, NO `port_scan`, NO `NetSession.connect`.
These are the ONLY correct patterns. Each was tested and runs in-game.

### Scan the local network (the port scanner pattern)

```
router = get_router                        // intrinsic: your gateway router
devices = router.devices_lan_ip            // list of LAN ip strings
for ip in devices
    ports = router.device_ports(ip)        // list of port objects (or null)
    if ports == null then continue
    for port in ports
        if port.is_closed then continue    // 1 = closed, 0 = open
        info = router.port_info(port)      // "http 1.0.0" style string
        print(ip + " : " + port.port_number + " " + info)
    end for
end for
```

`get_router` optionally takes an ip: `get_router("192.168.0.1")` returns that
network's router (or null).

### Reachability

```
r = get_shell.ping("1.1.1.1")   // 1 reachable, 0 not, string on invalid ip
```

### Login to a remote service (SSH/FTP only)

```
shell = get_shell
result = shell.connect_service(ip, port, user, password)
// returns a NEW shell on success, or an error STRING on failure
if typeof(result) != "shell" then print("failed: " + result)
```

Service value defaults to ssh; ftp services usually run on port 21. Connecting
leaves a log entry.

### Exploit reconnaissance (metaxploit)

```
metax = include_lib("/lib/metaxploit.so")  // real lib, on most machines
ns = metax.net_use(target_ip, port)        // NetSession or null
if ns != null then
    lib = ns.dump_lib                      // metaLib of the running service
    // metax.scan(lib) etc for vulnerabilities — see metaxploit docs
end if
```

A NetSession is ONLY obtained through `net_use` — never `new NetSession`.

`nslookup("google.com")` resolves a web address to an ip (or the string
"Not found").

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

<!-- api-reference: generated below, do not edit past this line -->

## Complete API reference

Generated from the official Grey Hack API metadata. `property` forms (no
parens) are member accesses; `method(...)` forms are calls. Examples are
prefixed with `>`. Arguments marked `?` are optional.

### Global functions

- `mail_login(user, pass)` → `metaMail` | `string` | `null`
- Returns a `MetaMail` entity if the login was successful. On failure a `string` with details gets returned. In case any of the provided values deviate from the types defined in the signature this method will return `null`. Utilizing this method in an SSH encryption process will trigger an error, halting further script execution.

- > metaMail = mail_login("test@test.com", "test")
- > if metaMail == null then
- > print("Loggin failed.")
- > else
- > print("You've got mail.")
- > end if
- `parent_path(directory)` → `string`
- Returns a `string` which is the parent path of the provided path. The path provided needs to be properly formatted. If the path is any other type than a `string` or is empty, this method will throw an error interrupting further script execution.

- > print("Is proper parent path: " + (parent_path("/my/test/path") == "/my/test"))
- `hasIndex(value, index)` → `number` | `null`
- Verifies if an index is available within an object. In case of success this method will return a `number` with the value one. In case of failure the value will be a zero. This method supports `map`s, `list`s and `string`s. Each passed type may result in different behavior therefore it is advisable to take a look at each of their specific signatures. In case an unsupported value gets passed this method will return `null`.

- > print("List has index: " + hasIndex([1, 2, 3], 2)
- `typeof(value)` → `string`
- Returns a `string` containing the type of the entity provided. There are following types by default: `"aptclientLib"`, `"blockchainLib"`, `"ctfEvent"`, `"coin"`, `"computer"`, `"pcomputer"`, `"ftpComputer"`, `"cryptoLib"`, `"debugLibrary"`, `"file"`, `"pfile"`, `"ftpFile"`, `"function"`, `"list"`, `"map"`, `"MetaLib"`, `"MetaMail"`, `"MetaxploitLib"`, `"NetSession"`, `"null"`, `"number"`, `"port"`, `"router"`, `"prouter"`, `"service"`, `"shell"`, `"ftpshell"`, `"pshell"`, `"SmartAppliance"`, `"string"`, `"subwallet"`, `"TrafficNet"`, `"wallet"`. Custom types can be added as well by using the `classID` property in a `map`.

- > myObj = { "classID": "myType" }
- > if typeof(myObj) == "myType" then
- > print("Object is myType.")
- > else
- > print("Object is not myType.")
- > end if
- `get_router(ipAddress?)` → `router` | `null`
- Returns by default the `router` to which the executing computer is connected to. Optionally an IP address can be provided. In case of failure `null` is returned. If there is no active internet connection, this method will throw an error, interrupting further script execution.

- > router = get_router
- > if router.local_ip == get_shell.host_computer.network_gateway then
- > print("Router is equal to network gateway.")
- > else
- > print("Router is not equal to network gateway.")
- > end if
- `get_switch(ipAddress)` → `router` | `null`
- Returns the switch on the local network whose IP address matches, otherwise it returns `null`.

- > router = get_switch("192.168.0.2)
- > print("IP address of switch: " + router.local_ip)
- `nslookup(webAddress)` → `string`
- Returns the IP address for the provided web address. In case the web address cannot be found a `string` gets returned containing the following message: `"Not found"`. If the provided web address is not a `string` or empty this method will throw an error preventing further script execution.

- > url = params[0]
- > print("IP for website is: " + nslookup(url))
- `print(value?, replaceText?)` → `null`
- Print a message on the Terminal. Optionally replacing can be enabled which will replace all previous prints. This can be useful for creating a loading bar for example. There is also the possibility of styling output by using TextMeshPro rich-text tags.

- > for i in range(9)
- > print(("#" * (9 - i)) + ("-" * i) , true)
- > wait(0.2)
- > end for
- `clear_screen` → `null`
- Removes any text existing in a Terminal prior to this point. Utilizing this method in an SSH encryption process will trigger an error, halting further script execution.

- > for i in range(9)
- > clear_screen
- > print(("#" * (9 - i)) + ("-" * i))
- > wait(0.2)
- > end for
- `active_user` → `string`
- Returns a `string` with the name of the user who is executing the current script.

- > print("Current active user: " + active_user)
- `home_dir` → `string`
- Returns a `string` with the home folder path of the user who is executing the current script.

- > print("Home dir of current user: " + home_dir)
- `get_shell(user?, pass?)` → `shell` | `null`
- Returns the `shell` that is executing the current script. Optionally, a username and password can be provided, allowing the use of a shell with other user privileges. If the username or password does not match an existing user or if the provided values deviate from the defined signature, this method will return `null`.

- > shell = get_shell("root", "test")
- > if shell == null then
- > print("Couldn't obtain root shell.")
- > else
- > print("Obtained root shell.")
- > end if
- `user_input(message?, isPassword?, anyKey?, addToHistory?)` → `string`
- Pauses script execution to receive input from the user. The prompt message can include TextMeshPro rich-text tags for styling. Input is submitted by pressing Enter. Optional parameters include isPassword, which masks the input with asterisks; anyKey, which allows capturing of individual key presses; and addToHistory, which saves the input to the input history, allowing it to be recalled with the arrow keys. Using this function during an SSH encryption process, or providing arguments that do not match the expected signature, will throw a runtime error and halt further script execution.

- > num = 0
- > aboveIncludingZeroTag = "<color=yellow>"
- > belowZeroTag = "<color=red>"
- > while (true)
- > clear_screen
- > output = aboveIncludingZeroTag + num
- > if (num < 0) then
- > output = belowZeroTag + num
- > end if
- > print(output)
- > key = user_input("Press arrow up/down to change value.", false, true)
- > if (key == "UpArrow") then
- > num = num + 1
- > else if (key == "DownArrow") then
- > num = num - 1
- > else
- > exit("Bye!")
- > end if
- > end while
- `include_lib(path)` → `crypto` | `metaxploit` | `service` | `blockchain` | `aptClient` | `smartAppliance` | `trafficNet` | `null`
- Enables the inclusion of library binaries, which can be used inside your script. If successful, an object related to the provided library will be returned; otherwise, `null` is returned. This function is exclusively for importing library binaries. If you want to import custom scripts or binaries into your project, use `import_code` instead. Passing anything other than a `string` for the path, or leaving the path empty, will cause an error to be thrown, interrupting further script execution.

- > crypto = include_lib("/lib/crypto.so")
- > if crypto == null then
- > print("Crypto library couldn't get imported.")
- > else
- > print("Crypto library got imported.")
- > end if
- `import_code(path)` → `null`
- Enables to import code from different sources into one file. This is useful in case you want to split code into different files and also to avoid any limitation in regards to text file character limits. Note that `import_code` requires an absolute path and is called while compiling the file into a binary instead of during runtime. Additionally `import_code` cannot be nested. Code can be either imported from plain text files or binaries that have `"allow import"` enabled. `import_code` is also parsed wherever it is found, not even a `//` comment will prevent it being evaluated.

- > //Content of main.src
- > import_code("/home/user/my_module.src")
- > print("bye")
- > //Content of my_module.src
- > print("hello!")
- `exit(message?)` → `null`
- Stops execution of the currently running script. Optionally a message can be provided which will be shown in the Terminal. There is also the possibility of styling output by using TextMeshPro rich-text tags.

- > while (true)
- > shouldExit = lower(user_input("Want to exit? (Y/N)"))
- > if (shouldExit == "y") then
- > exit("See you!")
- > end if
- > end while
- `user_mail_address` → `string` | `null`
- Returns a `string` containing the email address of the player who is executing the script. If the user does not have an email address this method will return `null`.

- > print("My EMail address is: " + user_mail_address)
- `user_bank_number` → `string` | `null`
- Returns a `string` containing the bank account number of the player who is executing the script. If the user does not have a bank this method will return `null`.

- > print("My Bank number is: " + user_bank_number)
- `whois(ip)` → `string`
- Returns a `string` containing the administrator information behind an IP address provided. In case of failure the returned `string` will contain an error message instead. If the provided ip is not a `string` or is empty this method will throw an error causing the script to stop.

- > adminInfo = whos("1.1.1.1")
- > infoLines = adminInfo.split(char(10))
- > infoObject = {}
- > infoObject.domainName = infoLines[0].split(":")[1].trim
- > infoObject.administrativeContact = infoLines[1].split(":")[1].trim
- > infoObject.emailAddress = infoLines[2].split(":")[1].trim
- > infoObject.phone = infoLines[3].split(":")[1].trim
- > print("Phone number: " + infoObject.phone)
- `wait(delay?)` → `null`
- Pauses the script execution. Optionally, the duration can be provided via the `time` argument. By default, the duration will be 1 second. The duration cannot be below 0.01 or above 300; otherwise, this method will throw a runtime exception.

- > start = time
- > wait(5)
- > elapsed = time - start
- > print("Waited: " + elapsed)
- `command_info(commandName)` → `string`
- Returns a `string` value of a translation. Translations include commands, documentation and other game-related things. Checkout Grey-Texts for an overview of all available keys. If the provided command name is not a `string` or is empty this method will throw an error causing the script to stop.

- > print(command_info("LS_USAGE"))
- `program_path` → `string`
- Returns a `string` containing the path of the script that is currently executing. It will update when using `launch`, which makes it different from `launch_path`.

- > path = program_path
- > print("Script gets executed within: " + parent_path(path))
- `current_path` → `string`
- Returns a `string` with the current active working directory. The working directory can be changed via the `cd` command.

- > path = current_path
- > print("My working directory is: " + path)
- `format_columns(columns)` → `string`
- Returns a `string` which is the formatted version of the provided text. Keep in mind that TextMeshPro rich-text tags might screw up the output. When using tags consider applying these after formatting. Passing anything other than a `string` will result in an empty `string`.

- > text = "FIRST SECOND THIRD
- > 1 2 3"
- > print(format_columns(text))
- `current_date` → `string`
- Returns a `string` containing the current date and time. Ingame time passes 15 times as fast as real-time - 4 seconds per in-game minute. The initial time after every wipe will be the 1st of January 2000 at 6:00 AM. Additionally, the game time will not proceed while the server is offline. * Output schema: `"[day]/[month]/[year] - [hours]:[minutes]"` * Example output: `"27/Jan/2000 - 08:19"`

- > dateStr = current_date
- > dateSegments = dateStr.split(" - ")
- > date = dateSegments[0].split("/")
- > day = date[0]
- > month = date[1]
- > year = date[2]
- > dateTime = dateSegments[1].split(":")
- > hours = dateTime[0]
- > minutes = dateTime[1]
- > print("Current day: " + day)
- `is_lan_ip(ip)` → `number`
- Returns a `number`. One indicates that the provided IP address is a valid LAN IP address. Otherwise, zero will be returned.

- > print("Is Lan IP: " + is_lan_ip("192.168.0.1"))
- `is_valid_ip(ip)` → `number`
- Returns a `number`. If the provided IP address is valid, its value will be one. Otherwise, its value is zero.

- > print("Is valid IP: " + is_valid_ip("1.1.1.1"))
- `bitwise(operator, left, right)` → `number` | `null`
- Returns a `number` by performing bitwise operations. Supported operators are: `"~"`, `"&"`, `"|"`, `"^"`, `"<<"`, `">>"`, `">>>"`. In case you want to use the tilde operator you only need to provide the operator and the left argument. If any of the required arguments is `null` this method will return `null`. Warning: If either operand is >= `0x80000000`, it'll always returns 0.

- > num = params[0].to_int
- > isOdd = bitwise("&", num, 1) == 1
- > if isOdd then
- > print("Number is odd.")
- > else
- > print("Number is even.")
- > end if
- `abs(value?)` → `number`
- Returns the absolute value of `number`.

- > a = 1
- > b = 5
- > difference = abs(a - b)
- > print("Difference between a and b is: " + difference)
- `acos(value?)` → `number`
- Returns the inverse cosine (in radians) of a `number`.

- > adjacent = 8
- > hypotenuse = 10
- > calcAngle = acos(adjacent / hypotenuse)
- > print("Angle: " + calcAngle)
- `asin(value?)` → `number`
- Returns the inverse sine (in radians) of a `number`.

- > opposite = 6
- > hypotenuse = 10
- > calcAngle = acos(opposite / hypotenuse)
- > print("Angle: " + calcAngle)
- `atan(y?, x?)` → `number`
- Returns the inverse tangent (in radians) of a `number`.

- > opposite = 8
- > hypotenuse = 10
- > calcAngle = atan(opposite / hypotenuse)
- > print("Angle: " + calcAngle)
- `tan(value?)` → `number`
- Returns the tangent of a `number` in radians.

- > degrees = 90
- > tanFromDegrees = tan(degress * pi / 180)
- > print("Tan from degrees: " + tanFromDegrees)
- `cos(value?)` → `number`
- Returns the cosine of a `number` in radians.

- > radians = 1
- > radius = 10
- > circleX = cos(radians) * radius
- > print(circleX)
- `code(value)` → `number`
- Returns the Unicode `number` of the first character of the string. In case an empty `string` is provided the script execution will crash.

- > key = user_input("Press a key!", false, true)
- > isA = key.code == 97
- > if isA then
- > print("You pressed A.")
- > else
- > print("You did not press A.")
- > end if
- `char(value?)` → `string`
- Returns the UTF-16 character `string` related to the provided unicode `number`. The provided `number` needs to be between 0 and 65535. Any `number` which is outside this range will cause the script to throw a runtime error. Beware when passing non-ASCII values to intrinsics as they will likely get re-encoded as UTF-8. For example, `md5(char(255))` will actually return the hash of the two-byte sequence `0xC3` `0xBF`.

- > key = user_input("Press a key!", false, true)
- > isA = key == char(97)
- > if isA then
- > print("You pressed A.")
- > else
- > print("You did not press A.")
- > end if
- `sin(value?)` → `number`
- Returns the sine of a `number` in radians.

- > radians = 1
- > radius = 10
- > circleY = sin(radians) * radius
- > print(circleY)
- `floor(value?)` → `number`
- Returns `number` rounded down to the integer value of the provided `number`.

- > price = 25.43467
- > floored = floor(price * 100) / 100
- > print("Floored price: " + floored)
- `range(start?, end?, inc)` → `[object Object]`
- Generates a `list` where each item is a `number`. By default, if only one argument is provided, the list starts at the given value and decrements by one for each item. You can optionally define a start and end value, as well as customize the incremental value. However, if the incremental value is zero, or if the list exceeds `16777215L` items, or if start/end is `null`, the function will throw a runtime error.

- > print("Countdown:")
- > for num in range(10)
- > print(num)
- > end for
- > print("Done!")
- `round(value?, fixed?)` → `number`
- Returns `number` rounded to the integer value of the provided `number`.

- > price = 25.43467
- > rounded = round(price * 100) / 100
- > print("Price: " + rounded)
- `rnd(seed)` → `number`
- Returns a random `number` between 0 and 1. Optionally a seed `number` can be provided.

- > min = 10
- > max = 20
- > output = floor(rnd * (max - min + 1) + min)
- > input = user_input("Guess a number between 10 and 20!").to_int
- > if (input == output) then
- > print("You guessed right!")
- > else
- > print("You failed! The number was " + output)
- > end if
- `sign(value?)` → `number`
- Returns a one or minus one, indicating the sign of the number passed as argument. If the input is zero, it will be returned as-is.

- > print(sign(40))
- > print(sign(-40))
- > print(sign(0))
- `sqrt(value?)` → `number`
- Returns the square root of a `number`.

- > a = 3
- > b = 4
- > calcHypotenuse = sqrt((a * a) + (b * b))
- > print("Hypotenuse: " + calcHypotenuse)
- `str(value)` → `string`
- Returns the `string` value of provided data. Can be used to turn a `number` into a `string` or to get the signature of a `function`.

- > signature = str(@user_input)
- > argSegment = signature[9:signature.len - 1]
- > args = argSegment.split(",")
- > print("Function has " + args.len + " arguments.")
- `ceil(value?)` → `number`
- Returns `number` rounded up to the integer value of the provided `number`.

- > price = 25.43467
- > upperPrice = ceil(price * 100) / 100
- > print("Upper price: " + upperPrice)
- `pi` → `number`
- Returns the `number` PI to the precision of six.

- > radius = 10
- > circumference = 2 * pi * radius
- > print("Circumference: " + circumference)
- `launch_path` → `string`
- Returns a `string` containing the path of the script that was initially executed, meaning that even when using `launch`, it will still return the path of the initially executed script.

- > path = launch_path
- > print("Script gets executed within: " + parent_path(path))
- `slice(value, startIndex?, endIndex)` → `list` | `string` | `null`
- Returns a sliced version of the passed object. Valid data types for slicing are `string` and `list`. The returned object will contain all elements related to the provided start and end index. If no start or end index is provided this method will essentially return a shallow copy of the passed object. If an invalid data type is passed, `null` is returned.

- > myString = "not your text"
- > print("my " + slice(myString, 9))
- `md5(value)` → `string`
- Returns the MD5 hash `string` of the provided `string`. Using this method within an SSH encryption process or passing anything other than a `string` will cause an error to be thrown, stopping any further script execution.

- > passwordHash = md5("test")
- > print("Hash for the password 'test' is " + passwordHash)
- `hash(value)` → `number`
- Returns numeric hash for the provided data. Using this method within a SSH encryption process will cause an error to be thrown causing the script execution to stop.

- > hashA = hash({ "a": 2, "b": 1 })
- > hashB = hash({ "b": 1, "a": 2 })
- > if (hashA == hashB) then
- > print("Objects are alike!")
- > else
- > print("Objects are different!")
- > end if
- `time` → `number`
- Returns a `number` of seconds representing the elapsed time since the script started.

- > start = time
- > for i in range(10000)
- > var = i * 100
- > end for
- > endTime = time - start
- > print("Script execution done within: " + endTime)
- `bitAnd(a?, b?)` → `number`
- Performs a bitwise AND for the provided values. Returns a `number`. Warning: If either operand is >= `0x80000000`, it'll always return 0.

- > print("Result of bitwise AND: " + bitAnd(1, 2))
- `bitOr(a?, b?)` → `number`
- Performs a bitwise OR for the provided values. Returns a `number`. Warning: If either operand is >= `0x80000000`, it'll always return 0.

- > print("Result of bitwise OR: " + bitOr(1, 2))
- `bitXor(a?, b?)` → `number`
- Performs a bitwise XOR for the provided values. Returns a `number`. Warning: If either operand is >= `0x80000000`, it'll always return 0.

- > print("Result of bitwise XOR: " + bitXor(1, 2))
- `log(value?, base?)` → `number`
- Returns the natural logarithm of a `number`. By default, the base is 10. Optionally the base can be changed.

- > a = 2
- > b = 8
- > baseLog = log(a) / log(b)
- > print("Base log is: " + baseLog)
- `yield` → `null`
- Waits for the next tick.

- > while (true)
- > yield
- > print("tick")
- > end while
- `get_custom_object` → `map`
- Returns `map` which is shared throughout script execution. Can be helpful if it desired to pass or receive values when using `launch`. Using this method in a SSH encryption process will cause an error to be thrown preventing further script execution.

- > get_custom_object.didScriptFail = true
- > someScriptContent = [
- > "print ""Done!""",
- > "get_custom_object.didScriptFail = false",
- > ].join(char(10))
- > myShell = get_shell("root", "test")
- > myComputer = myShell.host_computer
- > myComputer.touch("/root", "someScript.src")
- > someScriptFile = myComputer.File("/root/someScript.src")
- > someScriptFile.set_content(someScriptContent)
- > myShell.build("/root/someScript.src", "/root")
- > myShell.launch("/root/someScript")
- > if get_custom_object.didScriptFail then
- > print("Script did not finish successfully.")
- > else
- > print("Script finished successfully.")
- > end if
- `insert(object, index, value)` → `list` | `string`
- Inserts a value into either a `list` or a `string`. If the method is used on any other data type or the passed index is not a `number`, this method throws an error, preventing further script execution.

- > list = [2, 3, 4]
- > insert(list, 2, 42)
- > print("List with inserted item: " + list.join(", "))
- `join(value, delimiter?)` → `string`
- Returns a concatenated `string` containing all stringified values inside the `list`. These values will be separated via the provided separator. Passing anything other than a `list` will result in the original value being returned. In case the passed `list` exceeds `16777215L` items or the delimiter exceeds 128 characters, this method will throw an error, interrupting further script execution.

- > myList = [42, 1, 3]
- > print(join(myList, " .-*'*-. "))
- `reverse(value)` → `null`
- Reverses the order of all values in the `list`. This operation will mutate the `list`.

- > myList = [42, 1, 3]
- > reverse(myList)
- > print("Reversed list: " + myList.split(", "))
- `replace(value, oldVal, newVal, maxCount)` → `any`
- This function replaces a value within an object and returns the mutated object. Currently, it only supports `map`s and `list`s. Previously, it also supported `string`s, but that functionality has been replaced by `replace_regex`. If you use anything other than the supported types, a runtime error will be thrown.

- > list = [1,2,3,42]
- > newList = replace(list, 42, 4)
- > print(newList)
- `is_match(value, pattern, regexOptions?)` → `number`
- Uses regular expression to check if a string matches a certain pattern. If it matches, it will return a `number` with the value one. If it does not match, the value of the `number` will be zero. If any provided arguments deviate from the method signature types, if the pattern is empty, if the provided regexOptions are invalid, or if the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > hasWordAtTheEnd = is_match(myString, "\w+$")
- > print(hasWordAtTheEnd)
- `matches(value, pattern, regexOptions?)` → `[object Object]`
- Returns a `map` with all search results for the provided regular expression. Each key contains the index and the value contains the matching `string`. If any provided arguments deviate from the method signature types, if the pattern is empty, if the provided regexOptions are invalid, or if the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > result = matches(myString, "w")
- > print(result)
- `get_ctf(user, password, eventName)` → `ctfEvent` | `string`
- Returns `ctfEvent` object if there is one available. In case of failure this method will return a `string` with details.
- `reset_ctf_password(newPassword)` → `number` | `string`
- Resets the password of your CTF account. Returns a `number` with the value one if resetting was successful; otherwise, it will return a `string` containing the reason for failure.

- > reset_ctf_password("mysafepassword")
- `funcRef` → `[object Object]`
- Returns a `map` which enables to extend function references with custom methods.

- > funcRef.signature = function
- > return str(@self)
- > end function
- > print (@print).signature
- `list` → `[object Object]`
- Returns a `map` which enables to extend list types with custom methods.

- > list.map = function(callback)
- > newList = []
- > for item in self
- > newList.push(callback(item, __item_idx))
- > end for
- > return newList
- > end function
- > myMapFunction = function(item, index)
- > print "Mapping value at index: " + index
- > return item.myValue
- > end function
- > print [{ "myValue": 24 }].map(@myMapFunction)
- `map` → `[object Object]`
- Returns a `map` which enables to extend map types with custom methods.

- > map.extend = function(value)
- > for item in value
- > self[item.key] = item.value
- > end for
- > return self
- > end function
- > test = {"123":123}
- > test.extend({"bar": "foo"})
- > print "My extended value: " + test.bar
- `number` → `[object Object]`
- Returns a `map` which enables to extend number types with custom methods.

- > number.bitwise = function(operator, right)
- > return bitwise(operator, self, right)
- > end function
- > print (1234).bitwise(">>", 1)
- `string` → `[object Object]`
- Returns a `map` which enables to extend string types with custom methods.

- > string.color = function(colorValue = "red")
- > return "<color=" + colorValue + ">" + self + "</color>"
- > end function
- > print "My text: ".color + "Hello world".color("yellow")
- `get_abs_path(path, basePath?)` → `string`
- Returns the absolute path of the given path string. If the path is already absolute, it is returned unchanged. Otherwise, it is resolved against the current working path by default, or against the provided base path if specified. If the path exceeds 1024 characters, the base path exceeds 64 characters, or the arguments deviate from the expected signature, a runtime exception is thrown.

- > print("Absolute path of file in my current active path: " + get_abs_path("test.src"))
- `cd(path?)` → `string`
- Changes the current working directory of the active shell to the specified path. On success, an empty string is returned. If the operation fails, a descriptive error message is returned as a string. If this method is invoked during an SSH encryption process, or if the arguments deviate from the expected signature, a runtime error is thrown and further script execution is halted.

- > cd("/root")

### string methods

- `remove(value)` → `string`
- Returns a new `string` with the provided value removed. Any value other than `null` can be passed, but note that it will be cast to a string. If `null` is passed, this method will throw an error, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > newString = myString.remove("wrong")
- > print(newString + "right")
- `hasIndex(index)` → `number`
- Returns a `number`. If the provided index is available in the `string`, the value will be one. Otherwise, the value will be zero.

- > myString = "42 as an answer is wrong"
- > containsIndex = myString.hasIndex(1)
- > if containsIndex then
- > print("String contains index of 1.")
- > else
- > print("String does not contain index of 1.")
- > end if
- `insert(index, value)` → `string`
- Returns a `string` with the newly inserted `string` at the provided index. If the passed index is not a `number`, this method throws an error, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > index = myString.lastIndexOf("w") - 1
- > newString = myString.insert(index, "not ")
- > print(newString)
- `indexOf(value, offset)` → `number` | `null`
- Returns a `number` which indicates the first matching index of the provided value inside the `list`. Optionally a start index can be provided. In case the value does not exist inside the `string` a `null` gets returned.

- > myString = "42 as an answer is wrong"
- > index = myString.indexOf("wrong")
- > if index != null then
- > print("Invalid information spotted at: " + index)
- > else
- > print("Information seems valid.")
- > end if
- `lastIndexOf(searchStr)` → `number`
- Returns a `number` which indicates the last matching index of the provided value inside the `list`. In case the value does not exist inside the `string` a `-1` gets returned. If the provided searchStr is not a `string`, this method will return `null`.

- > myString = "42 as an answer is wrong"
- > index = myString.lastIndexOf("wrong")
- > if index != -1 then
- > print("Invalid information spotted at: " + index)
- > else
- > print("Information seems valid.")
- > end if
- `split(pattern, regexOptions?)` → `[object Object]` | `null`
- Returns a `list` where each item is a segment of the `string`, separated by the provided separator `string`. This method uses regular expressions for matching, so remember to escape special characters such as dots. If any of the provided arguments deviate from the method signature types, this method will return `null`. In case the pattern is empty, the provided regexOptions are invalid, or the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > segments = myString.split(" ")
- > if segments[0] != "42" then
- > print("Invalid information spotted!")
- > else
- > print("Information seems valid!")
- > end if
- `replace(pattern, newValue, regexOptions?)` → `string`
- Returns a `string` with the replaced content by using regular expressions. If any provided arguments deviate from the method signature types, if the pattern is empty, if the provided regexOptions are invalid or if the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > newString = myString.replace("wrong", "right")
- > print(newString)
- `trim` → `string`
- Returns a new `string` stripped of any spacing at the beginning and ending.

- > myString = " 42 "
- > print(myString.trim)
- `indexes` → `[object Object]`
- Returns a `list` where each item is a `number` representing all available indexes in the `string`.

- > myString = "42"
- > print(myString.indexes)
- `code` → `number`
- Returns a `number` representing the Unicode code of the first character of the `string`.

- > myString = "HELLO WORLD"
- > print(myString.code)
- `len` → `number`
- Returns a `number` representing the length of the `string`.

- > myString = "HELLO WORLD"
- > print("Size of string is: " + myString.len)
- `lower` → `string`
- Returns a new `string` in which all characters are transformed into lowercase.

- > myString = "HELLO WORLD"
- > print(myString.lower)
- `upper` → `string`
- Returns a new `string` in which all characters are transformed into uppercase.

- > myString = "hello world"
- > print(myString.upper)
- `val` → `number`
- Returns a `number` which is parsed from the `string`. In case the `string` is not numeric it will return a zero.

- > myString = "1.25"
- > print(myString.val + 40.75)
- `values` → `[object Object]`
- Returns a `list` where each item is a `string` representing all available characters in the `string`. Could be compared to using `split` but without any separator.

- > myString = "hello world"
- > print(myString.values)
- `to_int` → `string` | `number`
- Returns a `number` which is parsed from the `string` as an integer. In case the `string` is not numeric it will return the original `string`.

- > myString = "1"
- > print(myString.to_int + 41)
- `is_match(pattern, regexOptions?)` → `number`
- Uses regular expression to check if a string matches a certain pattern. If it matches, it will return a `number` with the value one. If it does not match, the value of the `number` will be zero. If any provided arguments deviate from the method signature types, if the pattern is empty, if the provided regexOptions are invalid, or if the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > hasWordAtTheEnd = myString.is_match("\w+$")
- > print(hasWordAtTheEnd)
- `matches(pattern, regexOptions?)` → `[object Object]`
- Returns a `map` with all search results for the provided regular expression. Each key contains the index and the value contains the matching `string`. If any provided arguments deviate from the method signature types, if the pattern is empty, if the provided regexOptions are invalid, or if the regular expression times out, an error will be thrown, preventing further script execution.

- > myString = "42 as an answer is wrong"
- > result = myString.matches("w")
- > print(result)

### list methods

- `remove(index)` → `null`
- Removes an item from the `list` with the provided index. Due to the removal the `list` will get mutated. If the passed index is `null` this method will throw an error preventing further script execution.

- > myList = [1, 42, 3]
- > myList.remove(1)
- > print("This list does not contain the answer to everything: " + myList.join(", "))
- `insert(index, value)` → `list`
- Inserts a value into the `list` at the index provided. Due to the insertion the `list` will get mutated. Returns the mutated `list`. If the passed index is not a `number`, this method throws an error, preventing further script execution.

- > myList = [1, 3]
- > myList.insert(1, 42)
- > print("This list does contain the answer to everything: " + myList.join(", "))
- `push(value)` → `list`
- Appends a value to the end of the `list`. This operation will mutate the `list`. Additionally, this method will return the updated `list`. However, it throws an error if you attempt to push a value into itself or into a map-like object such as a `file`, halting further script execution.

- > myList = [1, 3]
- > myList.push(42)
- > print("This list does contain the answer to everything: " + myList.join(", "))
- `pop` → `any`
- Returns and removes the last item in the `list`. This operation will mutate the `list`. If the `map` is empty, this method will return `null`.

- > myList = [1, 3, 42]
- > answer = myList.pop
- > print("Answer to everything: " + answer)
- `pull` → `any`
- Returns and removes the first item in the `list`. This operation will mutate the `list`. If the `map` is empty, this method will return `null`.

- > myList = [42, 1, 3]
- > answer = myList.pull
- > print("Answer to everything: " + answer)
- `shuffle` → `null`
- Shuffles all values in the `list`. This operation will mutate the `list`.

- > myList = [42, 1, 3]
- > myList.shuffle
- > print("New list order: " + myList.join(", "))
- `reverse` → `null`
- Reverses the order of all values in the `list`. This operation will mutate the `list`.

- > myList = [42, 1, 3]
- > myList.reverse
- > print("Reversed list: " + myList.join(", "))
- `sum` → `number`
- Returns sum of all values inside the `list`. Any non-numeric values will be considered a zero.

- > myList = [42, 1, 3]
- > sum = myList.sum
- > print("Sum of all items in list: " + sum)
- `hasIndex(index)` → `number`
- Returns a `number`. If the provided index is available in the `list`, the value will be one. Otherwise, the value will be zero.

- > myList = [42, 1, 3]
- > containsIndex = myList.hasIndex(1)
- > if containsIndex then
- > print("List contains index of 1.")
- > else
- > print("List does not contain index of 1.")
- > end if
- `indexOf(value, offset)` → `number` | `null`
- Returns a `number` which indicates the first matching index of the provided value inside the `list`. Optionally a start index can be provided. In case the value does not exist inside the `list` a `null` gets returned.

- > myList = [42, 1, 3]
- > index = myList.indexOf(42)
- > if index != null then
- > print("The answer for everything is at the following index: " + index)
- > else
- > print("No answer for everything found.")
- > end if
- `sort(key, ascending?)` → `list`
- Sorts the values of a `list` alphanumerically. This operation mutates the original `list`. Optionally, a key can be provided, which is used if the items are `map`s or `list`s. Finally, this method returns the updated `list`.

- > myList = [{ "key": 42 }, { "key": 2 }, { "key": 1 }]
- > myList.sort("key")
- > print(myList)
- `join(delimiter)` → `string`
- Returns a concatenated `string` containing all stringified values inside the `list`. These values will be separated via the provided separator. In case the `list` exceeds `16777215L` items or the delimiter exceeds 128 characters, this method will throw an error, interrupting further script execution.

- > myList = [42, 1, 3]
- > print(myList.join(" .-*'*-. "))
- `indexes` → `[object Object]`
- Returns a `list` containing all available indexes.

- > myList = [42, 1, 3]
- > for i in myList.indexes
- > print(myList[i])
- > end for
- `len` → `number`
- Returns a `number` representing the count of values inside the `list`.

- > myList = [42, 1, 3]
- > print("myList contains " + myList.len + " items")
- `values` → `list`
- Returns a `list` containing all available values. Note that this will not create a copy of the original `list`. The returned instance will the same as original `list`, so any mutations made to the returned `list` will also affect the original one.

- > myList = [42, 1, 3]
- > for v in myList.values
- > print(v)
- > end for
- `replace(oldVal, newVal, maxCount)` → `list`
- Returns updated `list` where each value matching with the provided replace argument gets replaced. This operation will mutate the `list`.

- > myList = [1, 2, 2, 7]
- > myList.replace(2, 3)
- > print(myList.join(""))

### map methods

- `remove(key)` → `number`
- Removes an item from the `map` with the provided key. Due to the removal, the `map` will get mutated. If the value is removed successfully, this method will return a `number` with the value one. If the removal fails, the value will be zero. Passing any map-like object, such as a file or computer, will cause an error to be thrown, stopping further script execution.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > myMap.remove("answer")
- > print(myMap)
- `push(key)` → `map`
- Adds the value 1 to the provided key. This operation will mutate the `map`. The updated `map` will be returned. However, it throws an error if you attempt to push a value into itself or into a map-like object such as a `file`, halting further script execution. If the passed key is `null` an error will be thrown as well.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > myMap.push("answer")
- > print(myMap.answer)
- `pull` → `any`
- Returns and removes the first item in the `map`. This operation will mutate the `map`. Passing a map-like object such as `file` or `computer` will result in an error, interrupting further script execution. If the `map` is empty, this method will return `null`.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > print(myMap.pull)
- `pop` → `any`
- Returns and removes the first item in the `map`. This operation will mutate the `map`. Passing a map-like object such as `file` or `computer` will result in an error, interrupting further script execution. If the `map` is empty, this method will return `null`.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > print(myMap.pop)
- `shuffle` → `null`
- Shuffles all values in the `map`. This operation will mutate the `map`.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > myMap.shuffle
- > print(myMap)
- `sum` → `number`
- Returns sum of all values inside the `map`. Any non-numeric values will be considered a zero.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > sum = myMap.sum
- > print("Sum of all items in map: " + sum)
- `hasIndex(key)` → `number`
- Returns a `number`. If the provided key is available in the `map`, the value will be one. Otherwise, the value will be zero.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > containsIndex = myList.hasIndex("answer")
- > if containsIndex then
- > print("Map contains the answer.")
- > else
- > print("Map does not contain the answer.")
- > end if
- `indexOf(value)` → `any`
- Returns a value which can be of any type since `map` keys can be of any type. In case the value does not exist inside the `map`, `null` is returned.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > key = myList.indexOf(42)
- > if key != null then
- > print("Map contains the answer.")
- > else
- > print("Map does not contain the answer.")
- > end if
- `indexes` → `list`
- Returns a `list` containing all available keys. Keys can be of any type.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > for key in myMap.indexes
- > print(myMap[key])
- > end for
- `len` → `number`
- Returns a `number` representing the count of items inside the `map`.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > print("myMap contains " + myMap.len + " items")
- `values` → `list`
- Returns a `list` containing all available values within `map`.

- > myMap = { "answer": 42, "bar": 23, "foo": "moo" }
- > for value in myMap.values
- > print(value)
- > end for
- `replace(oldVal, newVal, maxCount)` → `map`
- Returns updated `map` where each value matching with the provided replace argument gets replaced. This operation will mutate the `map`. In case this method gets used on a map-like object such as `file` this method will throw a runtime error.

- > myObject = { "answer": 45 }
- > myObject.replace(45, 42)
- > print(myObject.answer)

### any (fallback members)

- `insert(index, value)` → `list` | `string`
- Inserts a value into either a `list` or a `string`. If the passed index is not a `number`, this method throws an error, preventing further script execution.

- > list = [2, 3, 4]
- > list.insert(2, 42)
- > print("List with inserted item: " + list.join(", "))
- `indexOf(value, value, after)` → `any`
- Lookups index of value within `map`s, `list`s, or `string`s. For `list`s and `string`s, the behavior is very similar. On success, you'll receive a `number` representing the found index. On failure, it will return `null`. For `map`s, it's a bit different since the returned value could be of any type. On failure, it will return `null` as well.

- > index = "test".indexOf("e")
- > print("e is at: " + index)
- `hasIndex(value)` → `number`
- Verifies if an index is available within an object. In case of success this method will return a `number` with the value one. In case of failure the value will be a zero. This method supports `map`s, `list`s and `string`s. Each passed type may result in different behavior therefore it is advisable to take a look at each of their specific signatures.

- > print("List has index: " + [1, 2, 3].hasIndex(2)
- `remove(value)` → `number` | `null` | `string`
- Depending on the data type, this function will remove a value in the provided object, potentially mutating the object. This method works with `map`s, `list`s, and `string`s. Each passed type may support different types for the `key` argument. For example, using this method on a string would treat the key as a character index. Therefore, it is advised to review the signatures of each type. Passing a key with the type `null` may cause an error to be thrown, preventing further script execution.

- > list = [9, 3, 5, 7]
- > list.remove(5)
- > print("List after removal: " + list.join(", "))
- `push(value)` → `list` | `map`
- Allows pushing a value into an object, supporting `map`s and `list`s. However, it throws an error if you attempt to push a value into itself or into a map-like object such as a `file`, halting further script execution.

- > list = [0, 1, 2, 3, 4, 5]
- > list.push(42)
- > print("The answer to everything is: " + list.pop)
- `pull` → `any`
- When passing a `list` to this method, it will return the value at the first index and remove it from the `list`. Additionally, if a `map` is passed, it will always return the value corresponding to the first matching key and mutate the `map` object accordingly. However, passing a map-like object such as `file` or `computer` will result in an error, interrupting further script execution.

- > myList = [42, 1, 3]
- > answer = myList.pull
- > print("Answer to everything: " + answer)
- `pop` → `any`
- When passing a `list` to this method, it will return the value at the last index and remove it from the `list`. Additionally, if a `map` is passed, it will always return the value corresponding to the first matching key and mutate the `map` object accordingly. However, passing a map-like object such as `file` or `computer` will result in an error, interrupting further script execution.

- > list = [0, 1, 2, 3, 4, 5]
- > print("The last item is: " + list.pop)
- `shuffle` → `null`
- Randomizes content of an object. Valid data types for this method are `list` and `map`. In case a map-like object such as a `file` or `computer` a runtime exception will be thrown.

- > list = [0, 1, 2, 3, 4, 5]
- > list.shuffle
- > print("And the winner is: " + list[0])
- `sum` → `number`
- Returns a `number` representing the sum of all items within a `map` or a `list`.

- > list = [0, 1, 2, 3, 4, 5]
- > print("Sum of all items is: " + list.sum)
- `indexes` → `list`
- Returns a `list` containing all indexes or keys of the passed object. This method supports `map`s, `list`s, and `string`s. The type of each item may vary when using this method on a `map` since keys could be any type. The other types will return a `list` where each item is a `number`.

- > indexesOfStr = "test".indexes
- > print("Following indexes are available: " + indexesOfStr.join(", "))
- `len` → `number`
- Returns `number` indicating what size the object is.

- > length = "test".len
- > print("Length of string is: " + length)
- `values` → `list`
- Returns a `list` containing all values of an object.

- > indexesOfStr = "test".values
- > print("Following values are available: " + indexesOfStr.join(", "))

### Shell

- `host_computer` → `computer`
- Returns a `computer` related to the `shell`.

- > shell = get_shell
- > computer = shell.host_computer
- > print("Computer public IP is: " + computer.public_ip)
- `start_terminal` → `null`
- Launches an active terminal. The terminal's color will change, displaying the IP of the connected shell. Script execution will be stopped upon starting a new terminal, unless this is called from another script that was executed via `shell.launch`. In that case, you will enter the shell after closing your root-level script within that terminal window. Using this method within an SSH encryption process will cause an error to be thrown, preventing further script execution.

- > shell = get_shell
- > shell.start_terminal
- `build(pathSource, pathBinary, allowImport?)` → `string`
- Compiles a plain code file provided in the arguments to a binary. On success, the new binary will be available under the provided build folder. The binary name will be the same as the source file just without the file extension. Optionally, an allowImport flag can be set which enables the use of `import_code` on the binary. All provided paths must be absolute. Returns an empty string on success. On failure, it will return a string containing details about the reason for failure. In case any provided values deviate from the defined signature a runtime exception will be thrown.

- > shell = get_shell
- > computer = shell.host_computer
- > computer.touch(home_dir, "test.src")
- > computer.File(home_dir + "/test.src").set_content("print(""hello world"")")
- > buildResult = shell.build(home_dir + "/test.src", home_dir + "/Desktop")
- > if buildResult != "" then
- > print("There was an error while compiling: " + buildResult)
- > else
- > print("File has been compiled.")
- > end if
- `connect_service(ip, port, user, password, service?)` → `shell` | `ftpShell` | `string` | `null`
- Returns a `shell` if the connection attempt to the provided IP was successful. This method can only connect to ports running an SSH or FTP service. SSH services usually run on port 22 and FTP services usually on port 21. Keep in mind to pass the right service value depending on which service is going to be used. By default, it will use SSH as the service. Please note that connecting will leave a log entry. In case of failure, a string is returned containing details. If any provided arguments deviate from the method signature, if this method is run in an SSH encryption process, or if the computer is not connected to the internet, a runtime exception will be thrown.

- > shell = get_shell
- > connectionResult = shell.connect_service("1.1.1.1", 22, "test", "test")
- > if typeof(connectionResult) != "shell" then
- > print("There was an error while connecting: " + connectionResult)
- > else
- > print("Connected!")
- > end if
- `launch(program, params?)` → `string` | `number`
- Launches the binary located at the provided path. Optionally, parameters can be passed. Returns a `number`. If the launch was successful, the value will be one; otherwise, it will be zero. In some cases, a `string` will be returned containing an error message. If you need to share variables between a launched script and the current process, consider using `get_custom_object`. Note that launching a script is not asynchronous, meaning that the current script will pause its execution until the launched script finishes. If any provided values deviate from the method signature or it is used within an SSH encryption process, a runtime exception will be thrown. There is a cooldown of 2 seconds between launches to prevent abuse. If you attempt to launch a script during this cooldown period, the method will return zero.

- > shell = get_shell("root", "test")
- > shell.launch("/bin/cat", "/etc/passwd")
- `ping(ip)` → `string` | `number`
- Returns a `number`. If the remote address could be reached the value will be one, zero otherwise. Firewalls do not block ping requests. Passing an invalid ip will cause the method to return a `string` with an error message. If any provided arguments deviate from the method signature a runtime exception will be thrown.

- > shell = get_shell
- > isPingable = shell.ping("1.1.1.1")
- > if isPingable then
- > print("Ping was successful!")
- > else
- > print("Ping failed!")
- > end if
- `scp(file, folder, remoteShell, isUpload?)` → `number` | `string` | `null`
- Send a `file` to the `computer` related to the provided `shell`. You require permission to read the `file` on the `computer` from which you are uploading and write permissions in the folder of the `computer` you are trying to upload to. Via the optional isUpload parameter you can define the direction. In case of failure, this method will return a `string` with the cause. Otherwise, a `number` with the value one gets returned. If any of the passed arguments deviates from the types of the method signature, `null` will be returned. In case the `string` for sourceFile or destinationFolder is empty, an error will be thrown, preventing further script execution. Utilizing this method in an SSH encryption process will trigger an error, halting further script execution.

- > shell = get_shell
- > remoteShell = shell.connect_service("1.1.1.1", 22, "test", "test")
- > result = remoteShell.scp("/bin/ls", "/etc/", shell)
- > if typeof(result) == "string" then
- > print("There was an error while sending file: " + result)
- > else
- > print("File got sent successfully.")
- > end if

### Computer (File of a machine)

- `get_ports` → `[object Object]`
- Returns a `list` of `port`s on the `computer` that are active.

- > router = get_router
- > ports = get_shell.host_computer.get_ports
- > for port in ports
- > print("Info: " + router.port_info(port))
- > end for
- `get_name` → `string`
- Returns the hostname of the machine.

- > computerName = get_shell.host_computer.get_name
- > print("The name of your machine is " + computerName)
- `local_ip` → `string`
- Returns a `string` with the local IP address of the `computer`.

- > localIp = get_shell.host_computer.local_ip
- > print("Local ip:" + localIp)
- `public_ip` → `string`
- Returns a `string` with the public IP address of the `computer`.

- > publicIp = get_shell.host_computer.public_ip
- > print("Public ip:" + publicIp)
- `File(path)` → `file` | `null`
- Returns a `file` located at the path provided in the arguments. The path can be either relative or absolute. It's important to note that any `file` object can represent a folder as well. If the provided path cannot be resolved, meaning that no file or folder exists, this method will return `null`. Providing any other type than `string` or an empty value for the path will result in an error, interrupting the script execution.

- > filePath = "/etc/passwd"
- > file = get_shell.host_computer.File(filePath)
- > if file != null then
- > print(file.get_content)
- > else
- > print("File at given path " + filePath + " does not exist.")
- > end if
- `create_folder(path, folder?)` → `string` | `number`
- Creates a folder at the path provided in the arguments. There are certain limitations to creating a folder: the folder name has to be alphanumeric and below 128 characters. Creation will fail if there is already a folder in place or if there are lacking permissions. Additionally, there is a folder limit of about 250 in each folder and 3125 folders in the computer overall. In case the folder creation fails, the method will return a `string` with details. In case of success, it will return a `number` with the value one. Providing any type that deviates from the signature or using this method in an SSH encryption process will cause an error to be thrown, aborting further script execution.

- > path = "/home/" + active_user + "/Desktop"
- > hostComputer = get_shell.host_computer
- > createResult = hostComputer.create_folder(path, "myfolder")
- > if typeof(createResult) == "string" then
- > print("There was an error when creating the folder: " + createResult)
- > else
- > print("Folder got created at given path " + path)
- > end if
- `is_network_active` → `number`
- Returns a `number` with either the value one or zero. If the `computer` has internet access, the value will be one. If there is no internet access, it will return zero instead.

- > hostComputer = get_shell.host_computer
- > if hostComputer.is_network_active then
- > print("You're connected.")
- > else
- > print("You're not connected.")
- > end if
- `touch(path, fileName)` → `number` | `string`
- Creates an empty text `file` at the provided path. Certain limitations apply to file creation: the `file` name must be alphanumeric and below 128 characters. Creation will fail if there is already a `file` in place or if permissions are lacking. Additionally, there is a file limit of about 250 in each folder and 3125 files in the computer overall. In case of success, it returns a `number` with the value one. In case of failure, it returns a `string` with details. Using this method in an SSH encryption process will cause an error to be thrown, preventing any further script execution.

- > path = "/home/" + active_user + "/Desktop"
- > hostComputer = get_shell.host_computer
- > createResult = hostComputer.touch(path, "myFile.txt")
- > if typeof(createResult) == "string" then
- > print("There was an error when creating the file: " + createResult)
- > else
- > print("File got created at given path " + path)
- > end if
- `show_procs` → `string`
- Returns a `string` with an overview of all active processes on the `computer`, including information about the user, PID, CPU, memory, and command. Using this method in an SSH encryption process will cause an error to be thrown, preventing any further script execution.

- > hostComputer = get_shell.host_computer
- > procs = hostComputer.show_procs
- > list = procs.split(char(10))[1:]
- > processes = []
- > for item in list
- > parsedItem = item.split(" ")
- > process = {}
- > process.user = parsedItem[0]
- > process.pid = parsedItem[1]
- > process.cpu = parsedItem[2]
- > process.mem = parsedItem[3]
- > process.command = parsedItem[4]
- > processes.push(process)
- > end for
- > print(processes)
- `network_devices` → `string`
- Returns a `string` containing information about all network devices available on the `computer`. Each item includes details about the interface name, chipset, and whether monitoring support is enabled.

- > hostComputer = get_shell.host_computer
- > devices = hostComputer.network_devices
- > deviceList = devices.split(char(10))
- > for item in deviceList
- > print(item)
- > end for
- `change_password(username, password)` → `number` | `string` | `null`
- Changes the password of an existing user on the `computer`. Root access is necessary to successfully change the password. Passwords can only include alphanumeric characters and cannot exceed 15 characters. If the password change fails, this method will return a `string` containing information on why it failed. If the change succeeds, it will return a `number` with the value one. If the provided username is empty, an error will be thrown, preventing any further script execution. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > changeResult = hostComputer.change_password("test", "newPassword")
- > if typeof(changeResult) == "string" then
- > print("There was an error when changing the password: " + changeResult)
- > else
- > print("Password got successfully changed.")
- > end if
- `create_user(usename, password)` → `number` | `string` | `null`
- Creates a user on the `computer` with the specified name and password. Root access is necessary to successfully create a user. Both the username and password cannot exceed more than 15 characters and must be alphanumeric. There cannot be more than 15 users created on the same `computer`. If the creation fails, this method will return a `string` containing the reason for the failure. On success, it will return a `number` with the value one. If the provided username is empty or either of the values exceeds 15 characters, an error will be thrown, interrupting further script execution. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > creationResult = hostComputer.create_user("newUser", "123")
- > if typeof(creationResult) == "string" then
- > print("There was an error when creating an user: " + creationResult)
- > else
- > print("User got successfully created.")
- > end if
- `delete_user(username, removeHome?)` → `number` | `string` | `null`
- Deletes the indicated user from the `computer`. It can optionally delete the user's home folder as well, although by default the home folder will not be deleted. Root access is necessary to successfully delete a user. Keep in mind that you cannot delete the root user. If the deletion fails, this method will return a `string` containing the cause of failure. On success, it will return a `number` with the value one. If the provided username is empty, an error will be thrown, interrupting further script execution. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > deletionResult = hostComputer.delete_user("test", true)
- > if typeof(deletionResult) == "string" then
- > print("There was an error when deleting an user: " + deletionResult)
- > else
- > print("User got successfully deleted.")
- > end if
- `create_group(username, group)` → `number` | `string` | `null`
- Creates a new group associated with an existing user on the `computer`. Root access is necessary to successfully create a group. There are limitations when creating a group, such as a character limit of 15 and that the group name may only contain alphanumeric characters. If the group creation fails, this method will return a `string` containing the cause of failure. On success, it will return a `number` with the value one. If the provided arguments are empty or the username exceeds 15 characters, an error will be thrown, interrupting further script execution. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > creationResult = hostComputer.create_group("test", "staff")
- > if typeof(creationResult) == "string" then
- > print("There was an error when creating a group: " + creationResult)
- > else
- > print("Group got successfully created.")
- > end if
- `delete_group(username, group)` → `number` | `string` | `null`
- Deletes an existing group associated with an existing user on the `computer`. Root access is necessary to successfully delete a group. If the group deletion fails, this method will return a `string` containing the cause of failure. On success, it will return a `number` with the value one. If either of the provided values is empty, an error will be thrown, preventing further script execution. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > deletionResult = hostComputer.delete_group("test", "staff")
- > if typeof(deletionResult) == "string" then
- > print("There was an error when deleting a group: " + deletionResult)
- > else
- > print("Group got successfully deleted.")
- > end if
- `groups(username)` → `string` | `null`
- Returns a `string` containing groups associated with an existing user on the `computer`. If the user does not exist, a `string` with an error message will be returned. If the provided username is empty, an error will be thrown, preventing further script execution. If the provided username is anything other than a `string`, this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > hostComputer.create_group("root", "staff")
- > groups = hostComputer.groups("root")
- > listOfGroups = groups.split(char(10))
- > print(listOfGroups)
- `close_program(pid)` → `number` | `string` | `null`
- Closes a program associated with the provided PID. You can see the `list` of active programs by either using `show_procs` or typing ps into your terminal. To close a program, you need to either be the owner of the running process or root. If closing the program fails, this method will return a `string` containing details. On success, it will return a `number` with the value one. If there is no process with the provided PID, this method will return a `number` with the value zero. If the provided PID is anything other than a `number`, this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > processes = hostComputer.show_procs.split(char(10))[1:]
- > pid = processes[1].split(" ")[1]
- > closeResult = hostComputer.close_program(pid.to_int)
- > if typeof(closeResult) == "string" then
- > print("There was an error when closing a program: " + closeResult)
- > else
- > print("Program with pid " + pid + " got successfully closed.")
- > end if
- `wifi_networks(netDevice)` → `[object Object]` | `null`
- Returns a `list` of the Wi-Fi networks that are available for the provided interface. Each item in the `list` is a `string` containing information on the BSSID, PWR, and ESSID. If no matching netDevice can be found, this method will return `null`. If the active network card is not a Wi-Fi card, an error will be thrown, preventing any further script execution.

- > hostComputer = get_shell("root", "test").host_computer
- > networks = hostComputer.wifi_networks("wlan0")
- > result = []
- > for network in networks
- > parsedItem = network.split(" ")
- > item = {}
- > item.BSSID = parsedItem[0]
- > item.PWR = parsedItem[1]
- > item.ESSID = parsedItem[2]
- > result.push(item)
- > end for
- > print(result)
- `connect_wifi(netDevice, bssid, essid, password)` → `number` | `string` | `null`
- Connects to the indicated Wi-Fi network. It's not possible to connect to a new Wi-Fi while being logged in as a guest. If connecting to a new Wi-Fi fails, this method will return a `string` containing details. On success, it will return a `number` with the value one. Wi-Fi networks can be found via `wifi_networks` or by typing iwlist as a command in the terminal. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > hostComputer = get_shell.host_computer
- > networks = hostComputer.wifi_networks
- > firstNetwork = networks[0].split(" ")
- > BSSID = firstNetwork[0]
- > ESSID = firstNetwork[2]
- > connectionResult = hostComputer.connect_wifi("wlan0", BSSID, ESSID, "wifi-password")
- > if typeof(connectionResult) == "string" then
- > print("There was an error while connecting to new Wifi: " + connectionResult)
- > else
- > print("Connected to new Wifi successfully.")
- > end if
- `connect_ethernet(netDevice, address, gateway)` → `string` | `null`
- Sets up a new IP address on the computer through the Ethernet connection. It's not possible to set up a new IP address while being logged in as a guest. On failure, this method will either return a `string` with details or `null`. On success, it will return an empty `string`. If any of the provided parameters have a type that deviates from the defined signature or the computer is not connected to the internet, an error will be thrown, preventing any further script execution.

- > hostComputer = get_shell.host_computer
- > connectionResult = hostComputer.connect_ethernet("eth0", "192.168.0.4", get_router.local_ip)
- > if typeof(connectionResult) == "string" then
- > print("There was an error while connecting: " + connectionResult)
- > else
- > print("Connected successfully.")
- > end if
- `network_gateway` → `string`
- Returns a `string` with the gateway IP address configured on the computer.

- > hostComputer = get_shell.host_computer
- > gatewayIp = hostComputer.network_gateway
- > print("Gateway IP: " + gatewayIp)
- `active_net_card` → `string`
- Returns a `string` which contains either the keyword `"WIFI"` or `"ETHERNET"` depending on the connection type your computer is currently using.

- > hostComputer = get_shell.host_computer
- > netCard = hostComputer.active_net_card
- > print("Connected by: " + netCard)
- `reboot(safeMode?)` → `number` | `string` | `null`
- Reboots the computer. By default, it reboots in standard mode. If the optional safeMode parameter is provided and evaluates to a truthy value, the system will reboot in safe mode instead. On success, the method returns a `number` with the value one. If the reboot fails, a descriptive error message is returned as a `string`. If the argument type deviates from the expected signature, the method returns `null`. Calling this method in an SSH encryption process will trigger an error, halting further script execution.

- > hostComputer = get_shell.host_computer
- > signal = hostComputer.reboot(true)
- > if signal == 1 then
- > print("Reboot signal emitted successfully.")
- > else
- > print("There was an error when rebooting the computer: " + signal)
- > end if

### File and Folder

- `chmod(perms?, isRecursive?)` → `string`
- Modifies the `file` permissions. Optionally, these permissions can also be applied recursively. The format for applying permissions is as follows: `"[references][operator][modes]"`. The references type is defined through three possible types: user `"u"`, group `"g"`, and other `"o"`. The operator is used to define if permissions get added `"+"` or removed `"-"`. There are three different modes that can be modified: read `"r"`, write `"w"`, and execute `"x"`. So, for example, `"o-wrx"` would remove all possible permissions for others. To add all permissions for others again, `"o+wrx"` would be used. In case the modification fails, this method will return a `string` containing information about the reason. Otherwise, an empty `string` is returned. In case any type other than `number` is used for the `isRecursive` parameter, an error will be thrown preventing further script execution.

- > hostComputer = get_shell("root", "test").host_computer
- > rootFolder = hostComputer.File("/bin")
- > oldPermissions = rootFolder.permissions
- > rootFolder.chmod("o-wrx", true)
- > newPermissions = rootFolder.permissions
- > print("Old permissions: " + oldPermissions)
- > print("New permissions: " + newPermissions)
- `copy(path?, name?)` → `string` | `number` | `null`
- Copies the `file` to the provided path. Files can only be copied if the user has read and write permissions or is root. The new filename has to be below 128 characters and alphanumeric. After success, this method will return a `number` with the value one. Otherwise, it will return a `string` containing information about the reason for failure. If any of the parameter types deviate from the method signature, this method is used within an SSH encryption process, the new name exceeds 128 characters, or the path is too long, an error will be thrown, causing an interruption of script execution. In case the current file gets deleted, this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > copyResult = passwdFile.copy("/etc/", "duplicate")
- > if typeof(copyResult) == "string" then
- > print("There was an error while copying file: " + copyResult)
- > else
- > print("File got copied successfully.")
- > end if
- `move(path?, fileName?)` → `string` | `number` | `null`
- Moves the `file` to the provided path. Files can only be moved if the user has read and write permissions or is root. The new filename has to be below 128 characters and alphanumeric. After success, this method will return a `number` with the value one. Otherwise, this method will return a `string` with details. If any of the parameter types deviate from the method signature, this method is used within an SSH encryption process, the new name exceeds 128 characters, or the path is too long, an error will be thrown, causing an interruption of script execution. In case the current file gets deleted, this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > moveResult = passwdFile.move("/root/", "newFileName")
- > if typeof(moveResult) == "string" then
- > print("There was an error while moving file: " + moveResult)
- > else
- > print("File got moved successfully.")
- > end if
- `symlink(path?, newName?)` → `string` | `number` | `null`
- Creates a symlink to the specified path. Symlinks can only be created if the user has write permissions or is root. The new filename must be alphanumeric and under 128 characters. Upon success, this method returns a `number` with the value one. On failure, it returns a `string` with details. If any parameters deviate from the method signature, if used within an SSH encryption process, if the new name exceeds 128 characters, or if the path is too long, an error will be thrown, interrupting script execution. If the current file is deleted, this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > lsFile = hostComputer.File("/bin/ls")
- > symResult = lsFile.symlink("/bin", "alternativeLS")
- > if typeof(symResult) == "string" then
- > print("There was an error while creating symlink: " + symResult)
- > else
- > print("Symlink got created successfully.")
- > end if
- `rename(name?)` → `string` | `number`
- Rename the file with the name provided. Files can only be renamed if the user has write permissions or is root. The new filename has to be below 128 characters and alphanumeric. On failure, this method will return a `string` with details. Otherwise, this method will return an empty string. If this method is used within an SSH encryption process, an error will be thrown, causing the script execution to be interrupted. In case the provided name is `null`, this method will return a `number` with the value zero.

- > hostComputer = get_shell("root", "test").host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > renameResult = passwdFile.rename("renamed")
- > if typeof(renameResult) == "string" then
- > print("There was an error while renaming file: " + renameResult)
- > else
- > print("File got renamed successfully.")
- > end if
- `path(symlinkOrigPath?)` → `string`
- Returns a `string` containing the file path. If the file is a symlink, the optional `symlinkOrigPath` argument can be set to return the original path of the linked file instead. If the file has been deleted, this method will still return the path it had prior to deletion.

- > hostComputer = get_shell.host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > print("File location: " + passwdFile.path)
- `is_folder` → `number` | `null`
- Returns a `number`. The value is one if the file is a folder, zero otherwise. In case the file gets deleted this method will return `null` instead.

- > hostComputer = get_shell.host_computer
- > etcFolder = hostComputer.File("/etc")
- > print("Is a folder: " + etcFolder.is_folder)
- `parent` → `file` | `null`
- Returns the parent folder of the current file or folder. In case there is no parent folder `null` will be returned instead. In case the file gets deleted this method will return `null` as well.

- > hostComputer = get_shell.host_computer
- > etcFolder = hostComputer.File("/etc")
- > print("Parent path: " + etcFolder.parent.path)
- `name` → `string` | `null`
- Returns a `string` with the name of the file. In case the file gets deleted this method will return `null` instead.

- > hostComputer = get_shell.host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > print("Filename: " + passwdFile.name)
- `allow_import` → `number`
- Returns a `number`. If the file is binary and can be imported by other scripts, the value will be one; otherwise, the value will be zero. In case the file gets deleted, this method will cause a crash.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("File can be imported: " + lsBinary.allow_import)
- `get_content` → `string` | `null`
- Returns a `string` representing the content of the file. To read a file, the user requires read access or being root. Note that you cannot read a binary file. In case of failure, `null` will be returned. If this method is used within an SSH encryption process, an error will be thrown, preventing any further script execution.

- > hostComputer = get_shell("root", "test").host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > print("File content: " + passwdFile.get_content)
- `set_content(content?)` → `string` | `number` | `null`
- Saves text into a `file`. The content will not get appended to the `file`; therefore, existing content will be overridden. To set new content, the user requires write permissions or being root. Keep in mind that text files cannot exceed the character limit of 160,000. In case setting the content was successful, a `number` with the value one will be returned. Otherwise, a `string` with details will be returned. If this method is used within an SSH encryption process, an error will be thrown, preventing any further script execution. If the provided content is `null` or permissions are lacking, this method will return a `number` with the value zero. In case the file gets deleted this method will return `null`.

- > hostComputer = get_shell("root", "test").host_computer
- > passwdFile = hostComputer.File("/etc/passwd")
- > setResult = passwdFile.set_content("moo")
- > if typeof(setResult) == "string" then
- > print("There was an error while setting file content: " + setResult)
- > else if setResult == 0 then
- > print("Unable to set content of file!")
- > else
- > print("File content got changed successfully.")
- > end if
- `is_binary` → `number` | `null`
- Returns a `number`. If the file is a binary, the value will be one; otherwise, it will be zero. In case the file gets deleted, this method will return `null` instead.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("File is a binary: " + lsBinary.is_binary)
- `is_symlink` → `number` | `null`
- Returns a `number`. If the file is a symlink, the value will be one; otherwise, it will be zero. In case the file gets deleted, this method will return `null` instead.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("File is a symlink: " + lsBinary.is_symlink)
- `has_permission(perms?)` → `number` | `null`
- Returns a `number` indicating if the user who launched the script has the requested permissions. One will indicate that the user has the correct permissions. In case permissions are lacking, the value will be zero. There are three different permission types: read `"r"`, write `"w"`, and execute `"x"`. In case the file gets deleted, this method will return `null` instead.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("Is able to execute ls: " + lsBinary.has_permission("x"))
- `delete` → `string`
- Delete the current file. To delete files, write permissions are required or being root. In case of failure, a `string` with details will be returned. Otherwise, an empty `string` gets returned. Please note that deleting a file will leave a log entry.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > deletionResult = lsBinary.delete
- > if typeof(deletionResult) == "string" and deletionResult.len > 0 then
- > print("There was an error while deleting a file: " + deletionResult)
- > else
- > print("File got deleted successfully.")
- > end if
- `get_folders` → `[object Object]` | `null`
- Returns a `list` of folders. In case the current entity is a file instead of a folder this method will return `null`, so it is advisable to first use the `is_folder` function before calling this method. In case the current folder gets deleted this method will return `null` as well.

- > hostComputer = get_shell.host_computer
- > binFolder = hostComputer.File("/home")
- > folders = binFolder.get_folders
- > for folder in folders
- > print(folder.path)
- > end for
- `get_files` → `[object Object]` | `null`
- Returns a `list` of files. In case the current entity is a file instead of a folder this method will return `null`, so it is advisable to first use the `is_folder` function before calling this method. In case the current folder gets deleted this method will return `null` as well.

- > hostComputer = get_shell.host_computer
- > binFolder = hostComputer.File("/bin")
- > files = binFolder.get_files
- > for file in files
- > print(file.path)
- > end for
- `permissions` → `string` | `null`
- Returns a `string` with the current file permissions. In case the current file gets deleted, this method will return `null`. The format for this permissions `string` is as follows: `"[fileType]wrxwrxwrx"`. The file type is either `"d"` in case it's a directory or `"-"`. The user type gets defined through three possible types: user `"u"`, group `"g"`, and other `"o"`. There are three different permission types: read `"r"`, write `"w"`, and execute `"x"`. An example of a `string` returned by this method would be `"-rwxr-xr-x"`. Taking the latter as an example, the following things become clear: * The provided file is not a directory. * The user has full access. * The group and others have almost all permissions besides writing.

- > hostComputer = get_shell.host_computer
- > binFolder = hostComputer.File("/bin")
- > permissions = binFolder.permissions
- > fileType = permissions[0]
- > permissionsForUser = permissions[1:4]
- > permissionsForGroup = permissions[4:7]
- > permissionsForOther = permissions[7:10]
- > print("File type: " + fileType)
- > print("User permissions: " + permissionsForUser)
- > print("Group permissions: " + permissionsForGroup)
- > print("Other permissions: " + permissionsForOther)
- `owner` → `string` | `null`
- Returns a `string` with the name of the file owner. User permissions get applied to whoever is the owner of a file. In case the current file gets deleted, this method will return `null`.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("Owner of ls is: " + lsBinary.owner)
- `set_owner(owner?, recursive?)` → `string` | `null`
- Change the owner of this file. Optionally the owner can get applied recursively. The owner's name cannot exceed 15 characters. Additionally either write permissions or being root is required. In case of failure a `string` gets returned containing the cause. Otherwise an empty `string` gets returned. In case the current file gets deleted or the passed owner value is not a `string`, this method will return `null`. If the passed owner value is empty, the owner value is longer than 15 characters, or the passed recursive value deviates from its original type, an error will be thrown, interrupting further script execution.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > ownerResult = lsBinary.set_owner("root")
- > if typeof(ownerResult) == "string" then
- > print("There was an error while changing owner: " + ownerResult)
- > else
- > print("File owner changed successfully.")
- > end if
- `group` → `string` | `null`
- Returns a `string` with the name of the group to which this file belongs. Group permissions get applied to whoever is the owner of a file. In case the current file gets deleted, this method will return `null`.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > print("File is related to following group: " + lsBinary.group)
- `set_group(group?, recursive?)` → `string` | `null`
- Change the group related to this file. Optionally the group can get applied recursively. The group name cannot exceed 15 characters. Additionally either write permissions or being root is required. In case of failure, a `string` with details. On success, an empty `string` gets returned. In case the current file gets deleted or the passed group is not a `string`, this method will return `null`. If the passed group value is empty, the group value is longer than 15 characters, or the passed recursive value deviates from its original type, an error will be thrown, preventing further script execution.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > ownerResult = lsBinary.set_group("root")
- > if typeof(ownerResult) == "string" then
- > print("There was an error while changing group: " + ownerResult)
- > else
- > print("File group changed successfully.")
- > end if
- `size` → `string` | `null`
- Returns a `string` with the size of the file in bytes. There is no correlation between file size and actual file content. Instead, the file size is depending on the name of the file. In case the current file gets deleted, this method will return `null`.

- > hostComputer = get_shell.host_computer
- > lsBinary = hostComputer.File("/bin/ls")
- > size = lsBinary.size
- > if size.to_int > 1000 then
- > print("File size is bigger than 1000 bytes.")
- > else
- > print("File size is below 1000 bytes.")
- > end if

### Router

- `device_ports(ip)` → `string` | `[object Object]` | `null`
- Returns a `list` where each item is an open `port` related to the device of the provided LAN IP address. The device needs to be within the network of the `router`. In case of failure, this method will return `null` or a `string` with details. In case an empty ip is provided this method will throw a runtime exception.

- > router = get_router
- > devices = router.devices_lan_ip
- > for ip in devices
- > ports = router.device_ports(ip)
- > openPorts = []
- > for port in ports
- > if port.is_closed then continue
- > openPorts.push(port)
- > end for
- > if (openPorts.len == 0) then
- > print(ip + " has no open ports")
- > else
- > print(ip + " contains following open ports:")
- > for port in openPorts
- > print("|-" + port.port_number)
- > end for
- > end if
- > end for
- `devices_lan_ip` → `[object Object]`
- Returns a `list` where each item is a `string` representing a LAN IP address. All devices are within the network of the router and can be reached by using the `ping` method. Some of the devices might be behind a firewall.

- > router = get_router
- > devices = router.devices_lan_ip
- > for ip in devices
- > print(ip + " found!")
- > end for
- `bssid_name` → `string`
- Returns a `string` with the BSSID value of the router.

- > router = get_router
- > bssid = router.bssid_name
- > print("BSSID: " + bssid)
- `essid_name` → `string`
- Returns a `string` with the ESSID value of the router.

- > router = get_router
- > essid = router.essid_name
- > print("ESSID: " + essid)
- `firewall_rules` → `[object Object]`
- Returns a `list` where each item is a `string` containing a firewall rule.

- > router = get_router
- > rules = router.firewall_rules
- > print("Firewall rules: " + rules.join(", "))
- `kernel_version` → `string`
- Returns a `string` with the version of the `kernel_router.so` library.

- > router = get_router
- > version = router.kernel_version
- > print("Kernel router version: " + version)
- `local_ip` → `string`
- Returns a `string` with the local IP address of the router.

- > router = get_router
- > localIp = router.local_ip
- > print("Local IP: " + localIp)
- `public_ip` → `string`
- Returns a `string` with the public IP address of the router.

- > router = get_router
- > publicIp = router.public_ip
- > print("Public IP: " + publicIp)
- `used_ports` → `[object Object]`
- Returns a `list` where each item is a `port` used inside the router.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > print("Port " + port.port_number + " is available!")
- > end for
- `ping_port(port)` → `port` | `null`
- Returns a `port` that is behind the port `number` provided. In case the `port` does not exist `null` gets returned.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > pingedPort = router.ping_port(port.port_number)
- > if (pingedPort == null) then continue
- > print("Pinged " + pingedPort.port_number)
- > end for
- `port_info(port)` → `string` | `null`
- Returns a `string` with information about the provided port, including details about the running service and its version. For example, the output could be `"http 1.0.0"`. If the operation fails, `null` will be returned.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > info = router.port_info(port)
- > print(info)
- > end for

### Port

- `port_number` → `number`
- Returns the `number` which is used for the port.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > print("Port " + port.port_number + " is in use!")
- > end for
- `is_closed` → `number`
- Returns a `number`, where one indicates that the specified `port` is closed and zero indicates that the port is open.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > state = "open"
- > if (port.is_closed) then state = "closed"
- > print("Port " + port.port_number + " is " + state + "!")
- > end for
- `get_lan_ip` → `string`
- Returns a `string` containing the local IP address of the computer to which the port is pointing.

- > router = get_router
- > ports = router.used_ports
- > for port in ports
- > print("Port " + port.port_number + " is pointed to " + port.get_lan_ip + "!")
- > end for

### Service

- `install_service` → `number` | `string`
- Installs the necessary files for the correct functioning of the service and starts it. If the installation is completed successfully, it returns a `number` with the value one. In case of an error, it returns a `string` with details.

- > service = include_lib("/lib/libhttp.so")
- > result = service.install_service
- > if result == 1 then
- > print "Successfully installed service"
- > else
- > print "Service installation failed: " + result
- > end if
- `start_service` → `number` | `string`
- Starts the service and opens its associated `port` on the local machine. The service requires a port forwarded to the router to be accessible from the outside. If the service starts correctly, it returns a `number` with the value one. In case of an error, it returns a `string` with details.

- > service = include_lib("/lib/libhttp.so")
- > result = service.start_service
- > if result == 1 then
- > print "Successfully started service"
- > else
- > print "Starting service failed: " + result
- > end if
- `stop_service` → `number` | `string`
- Stops the service and closes its associated `port` on the local machine. If the service is stopped successfully, it returns a `number` with the value one. If an error occurs during the process, it returns a `string` with details. In some cases, the returned `number` might be zero, indicating that the service removal failed.

- > service = include_lib("/lib/libhttp.so")
- > result = service.stop_service
- > if result == 1 then
- > print "Successfully stopped service"
- > else
- > print "Stopping service failed: " + result
- > end if

### NetSession

- `dump_lib` → `metaLib`
- Returns the `metaLib` associated with the remote service. For example if the `metaxpoit` method `net_use` was used on a ssh port it will return the `metaLib` related to the ssh service. In case the port was zero is will return a `metaLib` related to the kernel router.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > metaLib = netSession.dump_lib
- > print("Library: " + metaLib.lib_name + " - " + metaLib.version + " on port " + ports[0].port_number)
- `get_num_conn_gateway` → `number`
- Returns the number of devices using this router as a gateway. If you obtained your `netSession` from a computer, it will fetch and return the value from its gateway router.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > print("Gateway clients: " + netSession.get_num_conn_gateway)
- `get_num_portforward` → `number`
- Returns the number of ports forwarded by this router. If you obtained your `netSession` from a computer, it will fetch and return the value from its gateway router.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > print("Port forwards: " + netSession.get_num_portforward)
- `get_num_users` → `number`
- Returns the number of user accounts on the system.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > print("User accounts: " + netSession.get_num_users)
- `is_any_active_user` → `number`
- Returns a `number`. If there is an active user on the system it will be one. Otherwise, it will be zero.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > print("User Active?: " + netSession.is_any_active_user)
- `is_root_active_user` → `number`
- Returns a `number`. If there is an active root on the system it will be one. Otherwise, it will be zero.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > print("Root Active?: " + netSession.is_root_active_user)
- `flood_connection` → `null`
- Initiates a DDoS attack targeting the computer associated with the currently active `netSession` object. To successfully force a reboot, there must be at least 4 concurrent `flood_connection` calls for every 1 unit of net speed on the target computer. Keep in mind that these calls need to come from different IPs. So for example PackS would require 12 active `flood_connection` calls. If the threshold is met, the target computer will be forced to reboot, and the terminal will output: `"remote connection interrupted"`. This method always returns `null` and only prints a message upon a successful attack.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > netSession = metax.net_use("1.1.1.1", ports[0].port_number)
- > netSession.flood_connection

### Metaxploit library (/lib/metaxploit.so)

- `load(path)` → `metaLib` | `null`
- Returns a `metaLib` object for the provided path to the library binary. Keep in mind that this can only be used on library files. On failure, this method will return `null`. If the provided path is empty, this method will throw a runtime exception, preventing further script execution.

- > metax = include_lib("/lib/metaxploit.so")
- > libFolder = get_shell.host_computer.File("/lib")
- > for file in libFolder.get_files
- > metaLib = metax.load(file.path)
- > print("Library: " + metaLib.lib_name + " - " + metaLib.version)
- > end for
- `net_use(ip, port?)` → `netSession` | `null`
- Returns a `netSession` object for the provided IP address and port. Note that if the port is set to zero, it will return a `netSession` related to the kernel router. The main purpose of this method is to gain a `netSession` and then use `dump_lib` to receive a `metaLib` object to exploit vulnerabilities. In case of failure, this method will return `null`. If this method is used within an SSH encryption process or with disabled internet, or if an invalid target IP is provided, this method will throw a runtime exception.

- > metax = include_lib("/lib/metaxploit.so")
- > ports = get_router("1.1.1.1").used_ports
- > for port in ports
- > netSession = metax.net_use("1.1.1.1", port.port_number)
- > metaLib = netSession.dump_lib
- > print("Library: " + metaLib.lib_name + " - " + metaLib.version + " on port " + port.port_number)
- > end for
- `rshell_client(ip, port?, processName?)` → `string` | `number` | `null`
- Launches a process on the victim's `computer`, silently attempting to continuously connect in the background to the specified address and port. For the reverse shell to run successfully, the `rshell` service must be installed, and the port forward must be configured correctly on the machine where the server is waiting for the victim's connection. If the launch was successful, a `number` with the value one will be returned. In case of failure, a `string` with details will be returned.

- > metax = include_lib("/lib/metaxploit.so")
- > metax.rshell_client("1.1.1.1", 1222, "bgprocess")
- `rshell_server` → `string` | `[object Object]`
- This method returns a `list` of `shell` objects that have been reverse shell connected to this computer. To manage the connections received, the `rshell` service must be installed on the machine that receives the victims' connections. In case of failure a `string` will be returned with details.

- > metax = include_lib("/lib/metaxploit.so")
- > shells = metax.rshell_server
- > firstShell = shells[0]
- > firstShell.host_computer.File("/").chmod("o-wrx", true)
- `scan(metaLib)` → `[object Object]` | `null`
- Returns a `list` where each item is a `string` representing a memory area which has vulnerabilities related to the provided library. These memory areas can be used to make further scans via `scan_address`. In case of failure, this method returns `null` instead. An example of a memory area would be "0x7BFC1EAA". Using this method within a SSH encryption process will throw a runtime exception.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > scanResult = metax.scan(metaLib)
- > for area in scanResult
- > print("Memory area containg vulnerability: " + area)
- > end for
- `scan_address(metaLib, memoryAddress)` → `string` | `null`
- Returns a `string` containing information about each vulnerability in the provided library and memory area. In case the scanning fails this method will return `null`. Using this method within a SSH encryption process will throw a runtime exception.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > scanResult = metax.scan(metaLib)
- > scanAddress = metax.scan_address(metaLib, scanResult[0])
- > segments = scanAddress.split("Unsafe check: ")[1:]
- > exploits = []
- > for segment in segments
- > labelStart = segment.indexOf("<b>")
- > labelEnd = segment.indexOf("</b>")
- > exploits.push(segment[labelStart + 3: labelEnd])
- > end for
- > print("Available vulnerabilities: " + exploits.join(", "))
- `sniffer(saveEncSource?)` → `string` | `null`
- The terminal listens to the network packets of any connection that passes through the computer. When any connection information gets captured, it will print a `string` with the obtained data. In case saving of encryption source is enabled it will download the source code of the script responsible for encryption. In case the operation fails this method will return `null`. Using this method within a SSH encryption process will throw a runtime exception.

- > metax = include_lib("/lib/metaxploit.so")
- > result = metax.sniffer
- > print(result)

### MetaLib (result of NetSession.dump_lib)

- `overflow(memoryAddress, unsecZone, optArgs?)` → `string` | `number` | `shell` | `computer` | `file` | `null`
- Exploits vulnerabilities in target systems by executing various attack vectors against libraries located in the `"/lib"` folder. The function requires a memory address, vulnerability identifier, and optional arguments that are mandatory for password changes (new password) and computer exploits (LAN IP address). Invalid argument types will cause a runtime exception to be thrown immediately. The system validates that the target library exists and is properly located in the `"/lib"` directory before proceeding otherwise it will return `null`. If the network where the library is located is disabled, the function returns a `string` indicating the network status. The exploit will fail and return `null` if the target is behind a firewall or if any of the specific vulnerability requirements aren't met, such as insufficient registered users, missing required libraries with correct versions, inadequate port forwards, absence of required user types like active guests or root users, or invalid file paths. If the target vulnerability is identified as a zero-day exploit, the system will load the appropriate zero-day vulnerability before execution. During execution, if a super admin intercepts the exploit attempt, user privileges are automatically lowered to guest level. Shell exploits, once all requirements are met, always return a `shell` object. Random folder exploits return a `file` object if the specified path exists or `null` if the folder cannot be found. Password change exploits return 1 for successful password modification or 0 for failure due to guest user restrictions, invalid alphanumeric format, or exceeding the 15-character limit. Settings override exploits work only on smart appliances like fridges or microwaves and return 1 for success or 0 for failure. Traffic light exploits require targets on the police station's network and return 1 for success or 0 for failure. Firewall exploits need router targets and return 1 for success or 0 for failure. Computer exploits return a `computer` object when successful or 0 if the LAN IP is invalid, the computer doesn't exist, or no non-root user is available. Using typeof to verify return value types is essential before processing results due to the variety of possible return types. To get a detailed overview you can also take a look at the following flowchart: Flowchart link

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > scanResult = metax.scan(metaLib)
- > target = scanResult[0]
- > scanAddress = metax.scan_address(metaLib, target)
- > segments = scanAddress.split("Unsafe check: ")
- > exploit = null
- > for segment in segments
- > hasRequirement = segment.indexOf("*") != null
- > if (not hasRequirement) then
- > labelStart = segment.indexOf("<b>")
- > labelEnd = segment.indexOf("</b>")
- > exploit = segment[labelStart + 3: labelEnd]
- > end if
- > end for
- > if (exploit) then
- > print("Exploiting... " + target + ":" + exploit)
- > print(metaLib.overflow(target, exploit))
- > else
- > print("No exploit found with zero requirements")
- > end if
- `version` → `string`
- Returns a `string` containing the version number of the library. An example of a version number would be `"1.0.0"`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > print("Init.so version: " + metaLib.version)
- `lib_name` → `string`
- Returns a `string` containing the name of the library. An example of a name would be `"init.so"`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > print("Name for library is: " + metaLib.lib_name)
- `debug_tools(user, password)` → `string` | `debugLibrary` | `null`
- Returns a library in debug mode as a `debugLibrary` object. A valid Neurobox engineer's username and password are required to access this mode. If successful, the `debugLibrary` object is returned; in case of an error, a `string` with details is provided. Passing values that deviate from the defined signature will result in `null`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > debugLib = metaLib.debug_tools("test", "test")
- > if typeof(debugLib) == "debugLibrary" then
- > print("Received debug libary object!")
- > end if
- `is_patched(getdate)` → `number` | `string` | `null`
- Returns by default a number indicating whether the library has been patched. A value of one indicates that the library has been patched, while zero indicates that it has not. If the getdate parameter is set to `true`, the function will return a `string` containing the date of the last patch. The data format is as follows: `"dd/MM/yyyy"`. Additionally if there is any error the return value will be a `string`. Providing values that deviate from the defined signature will cause `null` to be returned.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > isPatchedResult = metaLib.is_patched
- > if isPatchedResult == 1 then
- > print("init.so has been patched!")
- > end if

### MetaMail

- `delete(mailId)` → `number` | `string` | `null`
- Delete the email corresponding to the provided email ID. Returns a `number` with the value one if the email removal was successful. Otherwise, a `string` with an error message will be returned. If the provided mailId is anything other than a `string` this method will return `null`.

- > metaMail = mail_login(user_mail_address, "test")
- > mails = metaMail.fetch
- > results = []
- > for mail in mails
- > segments = mail.split(char(10))
- > mailId = segments[2][8:]
- > print(metaMail.delete(mailId))
- > end for
- > print("Deleted every mail!")
- `fetch` → `[object Object]` | `string`
- Returns a `list` where each item is a `string` containing mail id, from, subject and a small preview of the content consisting of the first 125 characters. If there is any issue a `string` will be returned with details.

- > metaMail = mail_login(user_mail_address, "test")
- > mails = metaMail.fetch
- > results = []
- > for mail in mails
- > segments = mail.split(char(10))
- > item = {}
- > item.mailId = segments[2][8:]
- > item.from = segments[3][6:]
- > item.subject = segments[4][9:]
- > item.preview = segments[5:]
- > results.push(item)
- > end for
- > print(results)
- `read(mailId)` → `string` | `null`
- Returns a `string` containing the content of a mail related to the provided mail id. The mail id argument can be obtained with `fetch`. In case the mail cannot be found this method will return "Mail not found". If the provided mailId is not a `string`, this method will return `null`.

- > metaMail = mail_login(user_mail_address, "test")
- > mails = metaMail.fetch
- > results = []
- > for mail in mails
- > segments = mail.split(char(10))
- > mailId = segments[2][8:]
- > print(metaMail.read(mailId))
- > end for
- `send(emailAddress, subject, message)` → `string` | `number` | `null`
- Send a new mail to the provided email address. Keep in mind that the subject can not exceed 128 characters and the message size should not exceed 2500 characters. Returns a `number` with the value one if the mail has been sent correctly, otherwise returns a `string` with an error. If any of the provided values deviate from the method signature, it will return `null`.

- > metaMail = mail_login(user_mail_address, "test")
- > result = metaMail.send(user_mail_address, "test subject", "test message")
- > if typeof(result) == "string" then
- > print("There was an error while sending mail: " + result)
- > else
- > print("Mail got send successfully.")
- > end if

### Crypto library (/lib/crypto.so)

- `aircrack(path)` → `string` | `null`
- Returns a `string` containing the password based on the file which was generated via aireplay. In case of failure, it will return `null` instead. If the provided path is empty, an error will be thrown, interrupting the script execution.

- > crypto = include_lib("/lib/crypto.so")
- > networks = get_shell.host_computer.wifi_networks("wlan0")
- > firstNetwork = networks[1].split(" ")
- > bssid = firstNetwork[0]
- > pwr = firstNetwork[1][:-1].to_int
- > essid = firstNetwork[2]
- > aireplayResult = crypto.aireplay(bssid, essid, 300000 / pwr)
- > if (aireplayResult == null) then
- > result = crypto.aircrack(home_dir + "/file.cap")
- > print(result)
- > end if
- `airmon(option, device)` → `number` | `string`
- Enables or disables the monitor mode of a network device. The `options` parameter can only be `"start"` or `"stop"`. Monitor mode can only be enabled on Wifi cards. If it wasn't possible to enable or disable the monitor mode, this method will return either a `number` with the value zero or a `string` with details. In case of success, it will return a `number` with the value one.

- > crypto = include_lib("/lib/crypto.so")
- > airmonResult = crypto.airmon("start", "wlan0")
- > if typeof(airmonResult) == "string" then
- > print("There was an error while switching monitoring mode: " + airmonResult)
- > else
- > print("Monitoring mode switched successfully.")
- > end if
- `aireplay(bssid, essid, maxAcks?)` → `string` | `null`
- Used to inject frames on wireless interfaces. Once the command with `"Control+C"` is stopped, it will save the captured information in a text file called `"file.cap"` in the path where the terminal is currently located. Alternatively, a maximum of captured `acks` can be specified for the command to stop automatically, saving the `"file.cap"` file as described above. To figure out how many ACKs are required, you can use the following formula: `"300000 / (Power + 15)"`. If there is an error, a `string` will be returned with the message indicating the problem. On success, it will return `null`, it is advised though to verify that the capture file actually exists. In case any of the provided values deviate from the signature types or bssid/essid is empty, an error will be thrown preventing any further script execution.

- > crypto = include_lib("/lib/crypto.so")
- > networks = get_shell.host_computer.wifi_networks("wlan0")
- > for index in range(0, networks.len - 1)
- > print(index + ".) " + networks[index])
- > end for
- > selectedIndex = user_input("Select Wifi: ").to_int
- > if (typeof(selectedIndex) == "string" or selectedIndex < 0 or selectedIndex > networks.len - 1) then
- > exit("Wrong index!")
- > end if
- > parsed = networks[selectedIndex].split(" ")
- > bssid = parsed[0]
- > pwr = parsed[1][:-1].to_int
- > essid = parsed[2]
- > potentialAcks = 300000 / (pwr + 15)
- > crypto.aireplay(bssid, essid, potentialAcks)
- > wifiPassword = crypto.aircrack("/home/" + active_user + "/file.cap")
- > print("Wifi password for " + essid + " is " + wifiPassword)
- `decipher(encPass)` → `string` | `null`
- Returns a decrypted password via the provided password MD5 hash. Keep in mind that this method is not decrypting a password but rather checking for existing passwords within the game world with a matching MD5 hash. So in case a password does not exist in the game world, the decryption will fail. On failure, this method will return `null`. Using this method in an SSH encryption process will cause an error to be thrown, aborting further script execution.

- > crypto = include_lib("/lib/crypto.so")
- > hostComputer = get_shell("root", "test").host_computer
- > passwdContent = hostComputer.File("/etc/passwd").get_content
- > firstAccount = passwdContent.split(char(10))[0]
- > parsed = firstAccount.split(":")
- > username = parsed[0]
- > passwordHash = parsed[1]
- > password = crypto.decipher(passwordHash)
- > print("User: " + username)
- > print("Password: " + password)
- `smtp_user_list(ip, port)` → `[object Object]` | `string` | `null`
- Returns a `list` of the existing users on the `computer` where the SMTP service is running. If these users also have an email account registered on the SMTP server, it will be indicated in the `list`. SMTP services are usually running on port `25`. In case of failure, this method will return a `string` containing the cause. If any of the provided values deviate from the signature types, this method will return `null`.

- > crypto = include_lib("/lib/crypto.so")
- > print(crypto.smtp_user_list("192.168.0.4", 25))
- `encrypt(filePath, password)` → `number` | `string` | `null`
- Encrypts the specified file using the provided key. On success, the method returns a `number` with the value one. If encryption fails, a descriptive error message is returned as a `string`. If any arguments deviate from the expected types defined in the method signature, the method returns `null`.

- > crypto = include_lib("/lib/crypto.so")
- > encryptionResult = crypto.encrypt("/etc/passwd", "mySecretKey")
- > if encryptionResult == 1 then
- > print("File got encrypted!")
- > else
- > print("Failed to encrypt file due to: " + encryptionResult)
- > end if
- `decrypt(filePath, password)` → `number` | `string` | `null`
- Decrypts the specified file using the provided key. On success, the method returns a `number` with the value one. If decryption fails, a descriptive error message is returned as a `string`. If any arguments deviate from the expected types defined in the method signature, the method returns `null`.

- > crypto = include_lib("/lib/crypto.so")
- > decryptionResult = crypto.decrypt("/etc/passwd", "mySecretKey")
- > if decryptionResult == 1 then
- > print("File got decrypted!")
- > else
- > print("Failed to decrypt file due to: " + decryptionResult)
- > end if
- `is_encrypted(filePath)` → `number` | `string` | `null`
- Checks whether the specified file is encrypted. Returns a `number` with the value one if the file is encrypted, or zero if it is not. If the check fails (e.g., due to a missing or unreadable file), a descriptive error message is returned as a `string`. If the argument does not match the expected type, the method returns `null`.

- > crypto = include_lib("/lib/crypto.so")
- > isEncrypted = is_encrypted(crypto, "/etc/passwd")
- > if isEncrypted == 1 then
- > print("File is encrypted!")
- > else
- > print("File is not encrypted!")
- > end if

### Blockchain library (/lib/blockchain.so)

- `coin_price(coinName)` → `null` | `string` | `number`
- Returns a `number` representing the current unit value of the cryptocurrency. In case of an error, a `string` with the error details will be returned. If the provided `coinName` is anything other than a `string`, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > price = blockchain.coin_price("test")
- > if typeof(price) == "string" then
- > exit "Couldnt get coin price due to: " + price
- > end if
- > print "Your coin price is " + price
- `show_history(coinName)` → `[object Object]` | `string` | `null`
- Returns a `map` with the latest changes in the value of a specific cryptocurrency. The key of the `map` is an index represented by a `number`. The value is a `list`, where index 0 is the historical price of the coin and index 1 is the date when the price change occurred. If the provided `coinName` is anything other than a `string` or if no coin exists with this name, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > history = blockchain.show_history("test")
- > if typeof(history) == "string" then
- > exit "Couldnt fetch history due to: " + history
- > else if history == null then
- > exit "There doesnt seem to be a coin"
- > end if
- > for entry in history.values
- > price = entry[0]
- > date = entry[1]
- > print "The price on " + date + " was " + price
- > end for
- `amount_mined(coinName)` → `string` | `number` | `null`
- Returns a `number` representing the total amount of mined coins. In case of an error, it will return a `string` with the details. If the provided coinName is anything other than a `string`, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > mined = blockchain.amount_mined("test")
- > if typeof(mined) == "string" then
- > exit "Couldnt get amount mined due to: " + mined
- > end if
- > print "Your mined amount is " + mined
- `get_coin(coinName, user, password)` → `string` | `coin` | `null`
- Returns a `coin` object used to manage the currency. In case of an error, it will return a `string` with the details. If any of the provided parameters deviate from the defined signature, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > if typeof(coin) != "coin" then
- > exit "Couldnt get coin object due to: " + coin
- > end if
- > print "Your coin address is " + coin.get_address
- `get_coin_name(user, password)` → `string` | `null`
- Returns a `string` with the name of the coin owned by the player. In case of an error, it returns a `string` with details. If any provided parameters deviate from the defined signature, this method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coinName = blockchain.get_coin_name("test", "test")
- > if not coinName.matches("^[A-Z]+$") then
- > exit "Couldnt get coin name due to: " + coinName
- > end if
- > print "The name of the coin you're owning is " + coinName
- `login_wallet(user, password)` → `string` | `wallet` | `null`
- Returns a `wallet` object on success. In case of an error, it will return a `string` indicating the reason. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > if typeof(wallet) == "string" then
- > print "Login failed due to: " + wallet
- > else
- > print "Login was successful!"
- > end if
- `create_wallet(user, password)` → `string` | `wallet` | `null`
- Creates a `wallet` and returns a `wallet` object on success, which can be used to manage cryptocurrencies. In case of an error, it will return a `string` with the details. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.create_wallet("test", "test")
- > if typeof(wallet) == "string" then
- > print "Wallet creation failed due to: " + wallet
- > else
- > print "Wallet creation was successful!"
- > end if
- `delete_coin(coinName, user, password)` → `number` | `string` | `null`
- Removes a cryptocurrency from the world. The credentials used in the creation of the cryptocurrency are required. On success, it will return a `number` with the value one. On failure, it will return a `string` containing details. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > result = blockchain.delete_coin("test", "test", "test")
- > if typeof(result) == "string" then
- > exit "Couldnt delete coin due to: " + result
- > end if
- > print "Coin got deleted"

### Wallet

- `list_coins` → `[object Object]` | `string`
- Returns a `list` where each item is a `string` with the names of the coins available in the `wallet`. On failure this method returns a `string` with an error message.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > print "My wallet is connected to: " + wallet.list_coins.join(", ")
- `get_balance(coinName)` → `number` | `string` | `null`
- Returns a `number` of coins of a given currency. In case of error, a `string` with the details is returned. If the passed coinName is anything other than a `string` this method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > for coinName in wallet.list_coins
- > print "You have " + wallet.get_balance(coinName) + " coins of the currency """ + coinName + """"
- > end for
- `buy_coin(coinName, coinAmount, unitPrice, subwalletUser)` → `number` | `string`
- Publishes a purchase offer indicating the number of coins you wish to buy and the price ($) per unit you are willing to pay. The purchase will be finalized if there is any sale offer with a price less than or equal to the one proposed in the purchase. If there is no eligible offer to sell at that time, the offer to buy will remain publicly visible until a new offer to sell satisfies the requirements. If the publication has been successful, a `number` with the value one is returned. In case of error, a `string` with the details is returned. Any deviation from the method signature will result in a runtime exception preventing further script execution.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = login_wallet(blockchain, "test", "test")
- > result = wallet.buy_coin("test", 100, 20, "test")
- > if result == 1 then
- > print "Sucessfully created purchase offer!"
- > else
- > print "Failed: " + result
- > end if
- `sell_coin(coinName, coinAmount, unitPrice, subwalletUser)` → `number` | `string`
- Publishes a sale offer indicating the amount of coins you want to sell and the price ($) per unit you want to assign. The sale will be finalized if there is any purchase offer with a price greater than or equal to that proposed in the sale. If there is no existing offer to buy that matches the requirements at that time, the offer to sell will remain publicly visible until a new offer to buy satisfies the requirements. If the publication has been successful, a `number` with the value one is returned. In case of error, a `string` with the details is returned. Any deviation from the method signature will result in a runtime exception preventing further script execution.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = login_wallet(blockchain, "test", "test")
- > result = wallet.sell_coin("test", 100, 20, "test")
- > if result == 1 then
- > print "Sucessfully created sell offer!"
- > else
- > print "Failed: " + result
- > end if
- `get_pending_trade(coinName)` → `string` | `list` | `null`
- Returns a `list` with the pending sale or purchase offer of this wallet for a certain currency. Index 0 of the `list` represents the type of offer with a `string` (Buy/Sell), index 1 represents the quantity to be sold or bought, and index 2 represents the price per unit. On failure, this method will return a `string` with details. Any deviation from the method signature will result in a `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > result = wallet.get_pending_trade("test")
- > isBuying = result[0] == "Buy"
- > quantity = result[1]
- > unitPrice = result[2]
- > currentBalance = wallet.get_balance("test")
- > if isBuying then
- > print "After buying was successful your balance will be " + (quantity * unitPrice + currentBalance)
- > else
- > print "After selling was successful your balance will be " + (currentBalance - quantity * unitPrice)
- > end if
- `cancel_pending_trade(coinName)` → `string` | `null`
- Cancel any pending offer of a certain coin. On success, an empty `string` will be returned. On failure, a `string` with an error message will be returned. Any deviation from the method signature will result in `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > if wallet.cancel_pending_trade("test") == "" then
- > print "Trade got canceled!"
- > end if
- `get_global_offers(coinName)` → `string` | `[object Object]` | `null`
- Returns a `map` with all the offers made by any player of a given currency. The key of the `map` represents the WalletID of the player who has made the offer, and the value of the `map` is a `list` where index 0 represents the type of offer with a `string` (Buy/Sell), index 1 represents the amount to sell or buy, and index 2 represents the price per unit. In case of failure, this method returns a `string` with details. Any deviation from the method signature will result in `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > for item in wallet.get_global_offers("test")
- > walletId = item.key
- > trade = item.value
- > isBuying = trade[0] == "Buy"
- > quantity = trade[1]
- > unitPrice = trade[2]
- > print "-" * 10
- > print "<b>" + walletId + "</b>"
- > if isBuying then
- > print "<color=green>Is buying</color>"
- > else
- > print "<color=yellow>Is selling</color>"
- > end if
- > print quantity + " coins with a unit price of " + unitPrice
- > end for
- `list_global_coins` → `string` | `[object Object]`
- Returns a `list` where each item is a `string` containing the names of all the currencies that exist. In case of failure, this method returns a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > print "All existing coins: " wallet.list_global_coins.join(", ")
- `show_nodes(coinName)` → `string` | `number` | `null`
- Returns a `number` representing the count of devices mining a specific coin for the same `wallet`. In case of an error, a `string` with details is returned. Any deviation from the method signature will result in `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = login_wallet(blockchain, "test", "test")
- > print "Active miners: " show_nodes(wallet, "test")
- `reset_password(newPassword)` → `number` | `string` | `null`
- Change the password of the wallet. Only the account owner can perform this action. If the process is completed successfully, a `number` with the value one will be returned. In case of an error, a `string` with details will be returned. Any deviation from the method signature will result in `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > wallet = blockchain.login_wallet("test", "test")
- > if wallet.reset_password("test") == 1 then
- > print "You got a new password!"
- > end if
- `get_pin` → `string`
- Returns a `string` with a PIN that refreshes every few minutes. This PIN is used to obtain an account in cryptocurrency services.

- > blockchain = include_lib("/lib/blockchain.so")
- > myShell = get_shell
- > myComputer = myShell.host_computer
- > wallet = blockchain.login_wallet("test", "test")
- > myComputer.touch("/root", "pin_launch.src")
- > myFile = myComputer.File("/root/pin_launch.src")
- > myFile.set_content("
- > blockchain = include_lib(""/lib/blockchain.so"")
- > myShell = get_shell
- > myComputer = myShell.host_computer
- > wallet = blockchain.login_wallet(""test"", ""test"")
- > if params[0] == wallet.get_pin then
- > get_custom_object.secret = ""The answer is 42""
- > else
- > get_custom_object.secret = ""The answer is 10053""
- > end if
- > ")
- > myShell.build("/root/pin_launch.src", "/root")
- > myFile.delete
- > myShell.launch("/root/pin_launch", wallet.get_pin)
- > print "The secret: " + get_custom_object.secret

### SubWallet

- `get_balance` → `number` | `string`
- Returns a `number` of coins of a given currency. In case of error, a `string` with the details is returned.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > subWallet = coin.get_subwallet("test")
- > print "Balance: " + subWallet.get_balance
- `set_info(info)` → `number` | `string`
- Stores optional information in the Subwallet for any use. Upon success, a `number` with the value one will be returned. In case of failure, a `string` with details will be returned.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > result = set_info(subWallet, "test")
- > if result == 1 then
- > print "Subwallet info got set!"
- > end if
- `get_info` → `string`
- Returns a `string` with the information stored by the coin creator.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > print "Subwallet info: " + get_info(subWallet)
- `delete` → `string` | `number`
- Deletes the account registered in the cryptocurrency. Returns a `number` where one indicates successful deletion and zero indicates failure. In case of certain failures, this method may return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > result = delete_subwallet(subWallet)
- > if result == 1 then
- > print "Subwallet got deleted!"
- > end if
- `get_user` → `string`
- Returns a `string` with the username associated with this subwallet. On failure, this method returns a `string` with an error message.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > print "Subwallet user: " + get_user(subWallet)
- `last_transaction` → `list` | `number` | `string`
- Returns a `list` with the information of the last transaction. Index 0 is a `string` with the other subWallet. Index 1 is an integer with the amount. Index 2 is a `number` indicating the direction of the transaction (0 for Deposit, 1 for Withdrawal). Index 3 is a `string` indicating the date of the transaction. On failure, this method will either return a `number` with the value zero or a `string` with an error message.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > transactionItem = last_transaction(subWallet)
- > destinationAccount = transactionItem[0]
- > amount = transactionItem[1]
- > direction = transactionItem[2]
- > completeDate = transactionItem[3]
- > if direction == 0 then
- > print "Received " + amount + " from " + destinationAccount + " got completed at the " + completeDate
- > else
- > print "Send " + amount + " to " + destinationAccount + " got completed at the " + completeDate
- > end if
- `mining` → `number` | `string`
- Starts the process of mining the cryptocurrency. The process leaves the terminal busy until a coin is mined. On success, this method will return a `number` with the value one. On failure, this method will return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > while mining(subWallet) == 1
- > print "Mining...", true
- > print "Balance " + get_balance_subwallet(subWallet)
- > end while
- `check_password(password)` → `number` | `string`
- Returns a `number` with the value one if the credentials are correct, otherwise, the value is zero. For some cases, this method will return a `string` with an error message.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > password = user_input("SubWallet password:", true)
- > if check_password(subWallet, password) == 1 then
- > print "Password is correct!"
- > end if
- `wallet_username` → `string`
- Returns a `string` with the name of the `wallet` to which this subwallet belongs.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = get_coin(blockchain, "test", "test", "test")
- > subWallet = get_subwallet(coin, "test")
- > print "SubWallet username: " + wallet_username(subWallet)

### Coin

- `set_cycle_mining(rateHours?)` → `string` | `number` | `null`
- Defines the interval (in-game hours) in which each user receives a coin reward when mining. The interval cannot be lower than 1 and not higher than 2160. If the provided `rateHours` is not a `number`, this method will return `null`. On success, it will return a `number` with the value one. In case of failure, the method will return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.set_cycle_mining(20)
- > if result == 1 then
- > print "Successful updated mining interval"
- > else
- > print "Failed updating mining interval"
- > end if
- `get_cycle_mining` → `string` | `number`
- Returns a `number` representing the defined interval in which each user receives a coin reward when mining. In case of failure, the method will return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_cycle_mining
- > if typeof(result) == "string" then
- > exit "Failed getting cyclic mining value due to: " + result
- > end if
- > print "cyclic mining value: " + result
- `get_reward` → `string` | `number`
- Returns a `number` representing the amount of coins that will be received as a reward after each mining cycle. In case of failure, the method will return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_reward
- > if typeof(result) == "string" then
- > exit "Failed getting reward value due to: " + result
- > end if
- > print "reward value: " + result
- `set_reward(coinAmount?)` → `number` | `string` | `null`
- Assigns the reward that miners will receive after each mining cycle. The reward value has to be above one. If the provided `coinAmount` is not a `number`, this method will return `null`. On success, it will return a `number` with the value one. In case of failure, the method will return a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.set_reward(-1)
- > if typeof(result) == "string" then
- > exit "Failed setting reward due to: " + result
- > end if
- > print "Successfully set reward!"
- `transaction(subWalletOrig, subWalletDest, valAmount)` → `string` | `number` | `null`
- Facilitates a transaction of the currency between the indicated subwallets. In case of an error, a `string` with the details is returned. In case of success, a `number` with a value of one will be returned. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.transaction("test", "test2", 20)
- > if typeof(result) == "string" then
- > exit "Failed transaction due to: " + result
- > end if
- > print "Successfully transfered!"
- `create_subwallet(walletID, pin, subWalletUser, subWalletPass)` → `string` | `number` | `null`
- Registers a new account in the `coin` that can be used to manage services such as stores. It is necessary to provide the PIN of the owner's `wallet` that wants to register. In case of success, the method will return a `number` with the value one. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`. In case of an error, a `string` with the details is returned.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > wallet = blockchain.login_wallet("test", "test")
- > result = coin.create_subwallet("test", wallet.get_pin, "test", "test")
- > if typeof(result) == "string" then
- > exit "Failed to create subwallet due to: " + result
- > end if
- > print "Successfully created subwallet!"
- `get_subwallet(subWalletUser)` → `string` | `subWallet` | `null`
- Returns a `subWallet` object on success. In case of error, it returns a `string` with the details. If the provided `subWalletUser` is not a `string`, this method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_subwallet("test")
- > if typeof(result) == "string" then
- > exit "Failed to get subwallet due to: " + result
- > end if
- > print "Successfully received subwallet!"
- `get_subwallets` → `string` | `[object Object]`
- Returns a `list` where each item is a `subWallet` object, including all the accounts registered in the cryptocurrency. In case of error, it returns a `string` with the details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_subwallets
- > if typeof(result) == "string" then
- > exit "Failed to get subwallets due to: " + result
- > end if
- > for subwallet in result
- > print subwallet.get_user + " has " + subwallet.get_balance + " coins"
- > end for
- `set_address(address)` → `number` | `string` | `null`
- Configures a valid address that will be shown to users who do not have the currency, indicating where to register. In case of an error, it returns a `string` with the details. In case of success, a `number` with a value of one will be returned. If the provided address is not a `string`, this method will return `null`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.set_address("12.12.12.12")
- > if typeof(result) == "string" then
- > exit "Failed to set address due to: " + result
- > end if
- > print "Successfully set address!"
- `get_address` → `string`
- Returns the configured address that will be shown to users who do not have the currency, indicating where they have to register. In case of an error, it returns a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_address
- > if not is_valid_ip(result) then
- > exit "Failed to get address due to: " + result
- > end if
- > print "address: " + result
- `get_mined_coins` → `string` | `number`
- Returns a `number` representing the amount of coins that have been mined so far. In case of an error, it returns a `string` with details.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.get_mined_coins
- > if typeof(result) == "string" then
- > exit "Failed to get mined coins due to: " + result
- > end if
- > print "mined coins: " + result
- `reset_password(newPassword)` → `number` | `string`
- Resets the password of the coin. It returns a `number` with the value one if resetting was successful; otherwise, it will return a `string`.

- > blockchain = include_lib("/lib/blockchain.so")
- > coin = blockchain.get_coin("test", "test", "test")
- > result = coin.reset_password("test")
- > if typeof(result) == "string" then
- > exit "Failed to reset password due to: " + result
- > end if
- > print "Successfully reset password"

### APT client library

- `show(repository)` → `string` | `null`
- Show displays all the packages available in a repository. The repository must be listed in the `"/etc/apt/sources.txt"` file. If the provided repository value is anything other than a `string`, this method will return `null`. If it cannot find a repository, it will return various error messages. On success, it will return a `string` containing all packages and their descriptions, with each entry separated by a newline.

- > aptClient = include_lib("/lib/aptclient.so")
- > packages = aptClient.show("177.202.15.132")
- > packageList = packages.split(char(10) + char(10))
- > packageList.pop // remove last empty item
- > for packageItem in packageList
- > entry = packageItem.split(char(10))
- > packageName = entry[0]
- > packageDescription = entry[1]
- > print "Title: <b>" + packageName + "</b>"
- > print "Description: <i>" + packageDescription + "</i>"
- > print "----------------------------"
- > end for
- `search(search)` → `string` | `null`
- Search specifically looks for a package in any of the repositories listed in `"/etc/apt/sources.txt"`. If the provided search value is anything other than a `string`, this method will return `null`. On success, it will return a `string` containing all packages that partially match the provided search value. On failure, it will return a `string` with various error messages.

- > aptClient = include_lib("/lib/aptclient.so")
- > packages = aptClient.search(".so")
- > packageList = packages.split(char(10) + char(10))
- > for packageItem in packageList
- > entry = packageItem.split(char(10))
- > if entry.len != 2 then
- > print "something wrong in: " + entry
- > continue
- > end if
- > packageName = entry[0]
- > packageDescription = entry[1]
- > print "Title: <b>" + packageName + "</b>"
- > print "Description: <i>" + packageDescription + "</i>"
- > print "----------------------------"
- > end for
- `update` → `string` | `number`
- Update refreshes the list of available packages after adding a new repository in `"/etc/apt/sources.txt"`, or if the remote repository has updated its information in `"/server/conf/repod.conf"`. If the update is successful, an empty `string` will be returned. In case of failure, a `string` with an error message will be returned. If for some reason the `"/etc/apt/sources.txt"` is malformed this method will return a number with the value zero.

- > aptClient = include_lib("/lib/aptclient.so")
- > result = aptClient.update
- > if result == "" then
- > print "Update successful!"
- > else
- > print "Error while updating: " + result
- > end if
- `add_repo(repository, port?)` → `string` | `null`
- Inserts a repository address into the `"/etc/apt/sources.txt"` file. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`. On success, it will return an empty `string`. In case of failure, it will return a `string` with an error message.

- > aptClient = include_lib("/lib/aptclient.so")
- > result = aptClient.add_repo("177.202.15.132")
- > if result == "" then
- > print "Addition successful!"
- > else
- > print "Error while adding: " + result
- > end if
- `del_repo(repository)` → `string` | `null`
- Deletes a repository address from the `"/etc/apt/sources.txt"` file. If the provided repository value is anything other than a `string`, this method will return `null`. On success, it will return an empty `string`. In case of failure, it will return a `string` with an error message.

- > aptClient = include_lib("/lib/aptclient.so")
- > result = aptClient.del_repo("177.202.15.132")
- > if result == "" then
- > print "Deletion successful!"
- > else
- > print "Error while deleting: " + result
- > end if
- `install(package, customPath?)` → `string` | `number` | `null`
- Installs a program or library from a remote repository listed in `"/etc/apt/sources.txt"`. If no path is specified, the program installs in `"/lib"` if it is a library or in `"/bin"` otherwise. If any of the provided parameters have a type that deviates from the defined signature, the method will return `null`. On success, this method will return a `number` with the value one. In case of failure, it will return a `string` containing an error message.

- > aptClient = include_lib("/lib/aptclient.so")
- > result = aptClient.install("rshell_interface")
- > if result == 1 then
- > print "Installed program successful!"
- > else
- > print "Error while installing: " + result
- > end if
- `check_upgrade(filepath)` → `string` | `number` | `null`
- Checks if there is a newer version of the program or library in the repository. If the provided filepath value is anything other than a `string`, this method will return `null`. On success, it will return a `number`, which can be either zero or one. Zero indicates that there is no new version, while one indicates that there is a new version available. In case of failure, it will return a string containing an error message.

- > aptClient = include_lib("/lib/aptclient.so")
- > result = aptClient.check_upgrade("/bin/rshell_interface")
- > if result == 0 then
- > print "Program doesnt need an update!"
- > else if result == 1 then
- > print "Program does need an update!"
- > else
- > print "Error while checking version: " + result
- > end if

### TrafficNet

- `camera_link_system` → `number` | `string`
- Accesses the traffic camera system, opening a window with controls to switch between different cameras. If the window opens successfully, this method returns a `number` with the value one. In case of an error, it returns a `string` with details.

- > libTraffic = include_lib("/lib/libtrafficnet.so")
- > linkSystemResult = libTraffic.camera_link_system
- > if linkSystemResult == 1 then
- > print("Initiated camera broadcast!")
- > end if
- `locate_vehicle(licensePlate, password)` → `number` | `string` | `null`
- Performs a search for the specified license plate to locate the vehicle. If the vehicle is visible on any camera, the viewer will switch to the camera currently displaying it and return a `number` with the value one. If the vehicle cannot be located or the license plate is incorrect, a `string` indicating the error is returned. If any of the provided values deviates from the defined types in the method signature, this method will return `null`.

- > libTraffic = include_lib("/lib/libtrafficnet.so")
- > libTraffic.camera_link_system
- > vehicleSearchResult = libTraffic.locate_vehicle("1L2M3N", "pass")
- > if vehicleSearchResult == 1 then
- > print("Found vehicle!")
- > end if
- `get_credentials_info` → `string`
- Returns string which contains job and name of a NPC. If an error occurs, a `string` with details is returned.

- > libTraffic = include_lib("/lib/libtrafficnet.so")
- > print(libTraffic.get_credentials_info)

### SmartAppliance

- `model` → `string`
- Returns a `string` with the appliance model ID.

- > libSmartapp = include_lib("/lib/libsmartappliance.so")
- > modelResult = libSmartapp.model
- > if modelResult.matches("^[A-Z]+$") then
- > print("Model is: " + modelResult)
- > else
- > print("Model couldn't be determined due to: " + modelResult)
- > end if
- `override_settings(power, temperature)` → `string` | `number` | `null`
- Overrides the power and temperature settings of the appliance. If successful, it returns a `number` with the value one; otherwise, it returns a `string` detailing the error. If any arguments deviate from the defined signature, this method will return `null`.

- > libSmartapp = include_lib("/lib/libsmartappliance.so")
- > overrideResult = libSmartapp.override_settings(1000, 20)
- > if overrideResult == 1 then
- > print("Override was successful!")
- > else
- > print("Override failed due to: " + overrideResult)
- > end if
- `set_alarm(enable)` → `string` | `number` | `null`
- Activates or deactivates the sound alarm indicating any appliance malfunction. If the operation is successful, a `number` with the value one is returned; otherwise, a `string` containing error details is returned. If the `enable` argument deviates from the defined signature, the method will return `null`.

- > libSmartapp = include_lib("/lib/libsmartappliance.so")
- > setAlarmResult = libSmartapp.set_alarm(false)
- > if setAlarmResult == 1 then
- > print("Alarm was disabled successfully!")
- > else
- > print("Disabling alarm failed due to: " + setAlarmResult)
- > end if

### FtpComputer

- `get_name` → `string`
- Returns the hostname of the machine.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > ftpComputerName = ftpComputer.get_name
- > print("The name of the ftp server is " + ftpComputerName)
- `File(path)` → `ftpFile` | `null`
- Returns a `ftpFile` located at the path provided in the arguments. The path can be either relative or absolute. It's important to note that any `ftpFile` object can represent a folder as well. If the provided path cannot be resolved, meaning that no file or folder exists, this method will return `null`. Providing any other type than `string` or an empty value for the path will result in an error, interrupting the script execution.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > file = ftpComputer.File("/etc/passwd")
- > if file.has_permission("r") then
- > ftpShell.scp("/etc/passwd", "/home/test/Desktop", shell)
- > else
- > print("No permissions to read passwd file.")
- > end if
- `create_folder(path, folder?)` → `string` | `number`
- Creates a folder at the path provided in the arguments. There are certain limitations to creating a folder: the folder name has to be alphanumeric and below 128 characters. Creation will fail if there is already a folder in place or if there are lacking permissions. Additionally, there is a folder limit of about 250 in each folder and 3125 folders in the computer overall. In case the folder creation fails, the method will return a `string` with details. In case of success, it will return a `number` with the value one. Providing any type that deviates from the signature or using this method in an SSH encryption process will cause an error to be thrown, aborting further script execution.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > createResult = ftpComputer.create_folder(path, "myfolder")
- > if typeof(createResult) == "string" then
- > print("There was an error when creating the folder: " + createResult)
- > else
- > print("Folder got created at given path " + path)
- > end if

### FtpFile

- `copy(path?, name?)` → `string` | `number` | `null`
- Copies the `file` to the provided path. Files can only be copied if the user has read and write permissions or is root. The new filename has to be below 128 characters and alphanumeric. After success, this method will return a `number` with the value one. Otherwise, it will return a `string` containing information about the reason for failure. If any of the parameter types deviate from the method signature, this method is used within an SSH encryption process, the new name exceeds 128 characters, or the path is too long, an error will be thrown, causing an interruption of script execution. In case the current file gets deleted, this method will return `null`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > passwdFile = ftpComputer.File("/etc/passwd")
- > copyResult = passwdFile.copy("/etc/", "duplicate")
- > if typeof(copyResult) == "string" then
- > print("There was an error while copying file: " + copyResult)
- > else
- > print("File got copied successfully.")
- > end if
- `move(path?, fileName?)` → `string` | `number` | `null`
- Moves the `file` to the provided path. Files can only be moved if the user has read and write permissions or is root. The new filename has to be below 128 characters and alphanumeric. After success, this method will return a `number` with the value one. Otherwise, this method will return a `string` with details. If any of the parameter types deviate from the method signature, this method is used within an SSH encryption process, the new name exceeds 128 characters, or the path is too long, an error will be thrown, causing an interruption of script execution. In case the current file gets deleted, this method will return `null`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > passwdFile = ftpComputer.File("/etc/passwd")
- > moveResult = passwdFile.move("/root/", "newFileName")
- > if typeof(moveResult) == "string" then
- > print("There was an error while moving file: " + moveResult)
- > else
- > print("File got moved successfully.")
- > end if
- `rename(name?)` → `string` | `number`
- Rename the file with the name provided. Files can only be renamed if the user has write permissions or is root. The new filename has to be below 128 characters and alphanumeric. On failure, this method will return a `string` with details. Otherwise, this method will return an empty string. If this method is used within an SSH encryption process, an error will be thrown, causing the script execution to be interrupted. In case the provided name is `null`, this method will return a `number` with the value zero.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > passwdFile = ftpComputer.File("/etc/passwd")
- > renameResult = passwdFile.rename("renamed")
- > if typeof(renameResult) == "string" then
- > print("There was an error while renaming file: " + renameResult)
- > else
- > print("File got renamed successfully.")
- > end if
- `path(symlinkOrigPath?)` → `string`
- Returns a `string` containing the file path. If the file is a symlink, the optional `symlinkOrigPath` argument can be set to return the original path of the linked file instead. If the file has been deleted, this method will still return the path it had prior to deletion.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > passwdFile = ftpComputer.File("/etc/passwd")
- > print("File location: " + passwdFile.path)
- `is_folder` → `number` | `null`
- Returns a `number`. The value is one if the file is a folder, zero otherwise. In case the file gets deleted this method will return `null` instead.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > etcFolder = ftpComputer.File("/etc")
- > print("Is a folder: " + etcFolder.is_folder)
- `parent` → `ftpFile` | `null`
- Returns the parent folder of the current file or folder. In case there is no parent folder `null` will be returned instead. In case the file gets deleted this method will return `null` as well.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > etcFolder = ftpComputer.File("/etc")
- > print("Parent path: " + etcFolder.parent.path)
- `name` → `string` | `null`
- Returns a `string` with the name of the file. In case the file gets deleted this method will return `null` instead.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > passwdFile = ftpComputer.File("/etc/passwd")
- > print("Filename: " + passwdFile.name)
- `is_binary` → `number` | `null`
- Returns a `number`. If the file is a binary, the value will be one; otherwise, it will be zero. In case the file gets deleted, this method will return `null` instead.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > print("File is a binary: " + lsBinary.is_binary)
- `is_symlink` → `number` | `null`
- Returns a `number`. If the file is a symlink, the value will be one; otherwise, it will be zero. In case the file gets deleted, this method will return `null` instead.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > print("File is a symlink: " + lsBinary.is_symlink)
- `has_permission(perms?)` → `number` | `null`
- Returns a `number` indicating if the user who launched the script has the requested permissions. One will indicate that the user has the correct permissions. In case permissions are lacking, the value will be zero. There are three different permission types: read `"r"`, write `"w"`, and execute `"x"`. In case the file gets deleted, this method will return `null` instead.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > print("Is able to execute ls: " + lsBinary.has_permission("x"))
- `delete` → `string`
- Delete the current file. To delete files, write permissions are required or being root. In case of failure, a `string` with details will be returned. Otherwise, an empty `string` gets returned. Please note that deleting a file will leave a log entry.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > deletionResult = lsBinary.delete
- > if typeof(deletionResult) == "string" and deletionResult.len > 0 then
- > print("There was an error while deleting a file: " + deletionResult)
- > else
- > print("File got deleted successfully.")
- > end if
- `get_folders` → `[object Object]` | `null`
- Returns a `list` of folders. In case the current entity is a file instead of a folder this method will return `null`, so it is advisable to first use the `is_folder` function before calling this method. In case the current folder gets deleted this method will return `null` as well.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > binFolder = ftpComputer.File("/home")
- > folders = binFolder.get_folders
- > for folder in folders
- > print(folder.path)
- > end for
- `get_files` → `[object Object]` | `null`
- Returns a `list` of files. In case the current entity is a file instead of a folder this method will return `null`, so it is advisable to first use the `is_folder` function before calling this method. In case the current folder gets deleted this method will return `null` as well.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > binFolder = ftpComputer.File("/bin")
- > files = binFolder.get_files
- > for file in files
- > print(file.path)
- > end for
- `permissions` → `string` | `null`
- Returns a `string` with the current file permissions. In case the current file gets deleted, this method will return `null`. The format for this permissions `string` is as follows: `"[fileType]wrxwrxwrx"`. The file type is either `"d"` in case it's a directory or `"-"`. The user type gets defined through three possible types: user `"u"`, group `"g"`, and other `"o"`. There are three different permission types: read `"r"`, write `"w"`, and execute `"x"`. An example of a `string` returned by this method would be `"-rwxr-xr-x"`. Taking the latter as an example, the following things become clear: * The provided file is not a directory. * The user has full access. * The group and others have almost all permissions besides writing.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > binFolder = ftpComputer.File("/bin")
- > permissions = binFolder.permissions
- > fileType = permissions[0]
- > permissionsForUser = permissions[1:4]
- > permissionsForGroup = permissions[4:7]
- > permissionsForOther = permissions[7:10]
- > print("File type: " + fileType)
- > print("User permissions: " + permissionsForUser)
- > print("Group permissions: " + permissionsForGroup)
- > print("Other permissions: " + permissionsForOther)
- `owner` → `string` | `null`
- Returns a `string` with the name of the file owner. User permissions get applied to whoever is the owner of a file. In case the current file gets deleted, this method will return `null`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > print("Owner of ls is: " + lsBinary.owner)
- `group` → `string` | `null`
- Returns a `string` with the name of the group to which this file belongs. Group permissions get applied to whoever is the owner of a file. In case the current file gets deleted, this method will return `null`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > print("File is related to following group: " + lsBinary.group)
- `size` → `string` | `null`
- Returns a `string` with the size of the file in bytes. There is no correlation between file size and actual file content. Instead, the file size is depending on the name of the file. In case the current file gets deleted, this method will return `null`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > lsBinary = ftpComputer.File("/bin/ls")
- > size = lsBinary.size
- > if size.to_int > 1000 then
- > print("File size is bigger than 1000 bytes.")
- > else
- > print("File size is below 1000 bytes.")
- > end if

### FtpShell

- `host_computer` → `ftpComputer`
- Returns a `computer` related to the `shell`.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > ftpComputer = ftpShell.host_computer
- > print("FTP public ip: " + ftpComputer.public_ip)
- `scp(sourceFile, destinationFolder, remoteShell, isUpload?)` → `number` | `string` | `null`
- Send a `file` to the `computer` related to the provided `shell`. You require permission to read the `file` on the `computer` from which you are uploading and write permissions in the folder of the `computer` you are trying to upload to. Via the optional isUpload parameter you can define the direction. In case of failure, this method will return a `string` with the cause. Otherwise, a `number` with the value one gets returned. If any of the passed arguments deviates from the types of the method signature, `null` will be returned. In case the `string` for sourceFile or destinationFolder is empty, an error will be thrown, preventing further script execution. Utilizing this method in an SSH encryption process will trigger an error, halting further script execution.

- > shell = get_shell
- > ftpShell = shell.connect_service("172.8.0.5", 21, "test", "test", "ftp")
- > putResult = ftpShell.scp("/bin/ls", "/etc/", shell)
- > if typeof(putResult) == "string" then
- > print("There was an error while sending file: " + putResult)
- > else
- > print("File got sent successfully.")
- > end if

### DebugLibrary

- `scan` → `string`
- Scans the library in debug mode to identify potential code errors that may lead to vulnerabilities. If issues are detected, the relevant code snippets are printed. In case of an error, a `string` containing the error message is returned.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > debugLib = metaLib.debug_tools("test", "test")
- > print("Debug Library result: " + debugLib.scan)
- `apply_patch(path)` → `string` | `null`
- Applies a patch containing corrected code to the specified text file at the provided path. Returns a `string` with the result of the operation. If the path argument is not a `string` this method will return `null`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > debugLib = metaLib.debug_tools("test", "test")
- > print("Path result: " + debugLib.apply_patch("/etc/passwd"))
- `unit_testing(errorLines)` → `string` | `null`
- Conducts automated tests on the specified lines of code. If potential vulnerabilities are detected due to errors in these lines, this method will print partial objects that could be obtained by exploiting the vulnerability, along with the affected memory zone and detailed vulnerability information. In case of failure, this function returns a `string` with an error message. If the `error lines` argument is not a `list`, the method will return `null`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > debugLib = metaLib.debug_tools("test", "test")
- > print("Unit test results: " + debugLib.unit_testing([1, 2, 3]))
- `payload(memZone, pathFile?)` → `string` | `[object Object]` | `null`
- Returns a `list` containing a single partial `computer` object if zero-day vulnerabilities are detected within the specified memory zone. If a file path is provided, a partial `file` object associated with this path will also be included in the `list`. Additionally, if this file is a library, its corresponding `metaLib` object is added to the returned `list`. In case of an error, a `string` with details is returned. Providing arguments that deviate from the defined signature will result in `null`.

- > metax = include_lib("/lib/metaxploit.so")
- > metaLib = metax.load("/lib/init.so")
- > debugLib = metaLib.debug_tools("test", "test")
- > result = debugLib.payload("0x7A69F4C3")
- > if typeof(result) == "list" and result.len > 0 then
- > print("Successfully executed payload!")
- > end if

### CtfEvent

- `get_description` → `string`
- Returns `string` with the CTF event description.
- `get_template` → `string`
- Returns `string` with the CTF event template.
- `player_success` → `number`
- Returns `number` with the value one if the CTF event got completed successfully. Otherwise this method will return a `number` with the value zero.
- `get_creator_name` → `string`
- Returns `string` with the name of the CTF event creator.
- `get_mail_content` → `string`
- Returns `string` with the mail content of the CTF event.
