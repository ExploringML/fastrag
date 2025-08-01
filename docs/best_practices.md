# FastHTML Best Practices


FastHTML applications are different to applications using FastAPI/react,
Django, etc. Don’t assume that FastHTML best practices are the same as
those for other frameworks. Best practices embody the fast.ai
philosophy: remove ceremony, leverage smart defaults, and write code
that’s both concise and clear. The following are some particular
opportunities that both humans and language models sometimes miss:

## Database Table Creation

**Before:**

``` python
todos = db.t.todos
if not todos.exists():
todos.create(id=int, task=str, completed=bool, created=str, pk='id')
```

**After:**

``` python
class Todo: id:int; task:str; completed:bool; created:str
todos = db.create(Todo)
```

FastLite’s `create()` is idempotent - it creates the table if needed and
returns the table object either way. Using a dataclass-style definition
is cleaner and more Pythonic. The `id` field is automatically the
primary key.

## Route Naming Conventions

**Before:**

``` python
@rt("/")
def get(): return Titled("Todo List", ...)

@rt("/add")
def post(task: str): ...
```

**After:**

``` python
@rt
def index(): return Titled("Todo List", ...) # Special name for "/"
@rt
def add(task: str): ... # Function name becomes route
```

Use `@rt` without arguments and let the function name define the route.
The special name `index` maps to `/`.

## Query Parameters over Path Parameters

**Before:**

``` python
@rt("/toggle/{todo_id}")
def post(todo_id: int): ...
# URL: /toggle/123
```

**After:**

``` python
@rt
def toggle(id: int): ...
# URL: /toggle?id=123
```

Query parameters are more idiomatic in FastHTML and avoid duplicating
param names in the path.

## Leverage Return Values

<div class="column-body-outset">

**Before:**

``` python
@rt
def add(task: str):
  new_todo = todos.insert(task=task, completed=False, created=datetime.now().isoformat())
  return todo_item(todos[new_todo])

@rt
def toggle(id: int):
  todo = todos[id]
  todos.update(completed=not todo.completed, id=id)
  return todo_item(todos[id])
```

**After:**

``` python
@rt
def add(task: str):
  return todo_item(todos.insert(task=task, completed=False, created=datetime.now().isoformat()))

@rt
def toggle(id: int):
  return todo_item(todos.update(completed=not todos[id].completed, id=id))
```

Both `insert()` and `update()` return the affected object, enabling
functional chaining.

</div>

## Use `.to()` for URL Generation

**Before:**

``` python
hx_post=f"/toggle?id={todo.id}"
```

**After:**

``` python
hx_post=toggle.to(id=todo.id)
```

The `.to()` method generates URLs with type safety and is
refactoring-friendly.

## PicoCSS comes free

**Before:**

``` python
style = Style("""
.todo-container { max-width: 600px; margin: 0 auto; padding: 20px; }
/* ... many more lines ... */
""")
```

**After:**

``` python
# Just use semantic HTML - Pico styles it automatically
Container(...), Article(...), Card(...), Group(...)
```

`fast_app()` includes PicoCSS by default. Use semantic HTML elements
that Pico styles automatically. Use MonsterUI (like shadcn, but for
FastHTML) for more complex UI needs.

## Smart Defaults

**Before:**

``` python
return Titled("Todo List", Container(...))

if __name__ == "__main__":
  serve()
```

**After:**

``` python
return Titled("Todo List", ...)  # Container is automatic

serve()  # No need for if __name__ guard
```

`Titled` already wraps content in a `Container`, and `serve()` handles
the main check internally.

## FastHTML Handles Iterables

**Before:**

``` python
Section(*[todo_item(todo) for todo in all_todos], id="todo-list")
```

**After:**

``` python
Section(map(todo_item, all_todos), id="todo-list")
```

FastHTML components accept iterables directly - no need to unpack with
`*`.

## Functional Patterns

List comprehensions are great, but `map()` is often cleaner for simple
transformations, especially when combined with FastHTML’s iterable
handling.

## Minimal Code

**Before:**

``` python
@rt
def delete(id: int):
  # Delete from database
  todos.delete(id)
  # Return empty response
  return ""
```

**After:**

``` python
@rt
def delete(id: int): todos.delete(id)
```

- Skip comments when code is self-documenting
- Don’t return empty strings - `None` is returned by default
- Use a single line for a single idea.

## Use POST for All Mutations

**Before:**

``` python
hx_delete=f"/delete?id={todo.id}"
```

**After:**

``` python
hx_post=delete.to(id=todo.id)
```

FastHTML routes handle only GET and POST by default. Using only these
two verbs is more idiomatic and simpler.

## Modern HTMX Event Syntax

**Before:**

``` python
hx_on="htmx:afterRequest: this.reset()"
```

**After:**

``` python
hx_on__after_request="this.reset()"
```

This works because:

- `hx-on="event: code"` is deprecated; `hx-on-event="code"` is preferred
- FastHTML converts `_` to `-` (so `hx_on__after_request` becomes
  `hx-on--after-request`)
- `::` in HTMX can be used as a shortcut for `:htmx:`.
- HTMX natively accepts `-` instead of `:` (so `-htmx-` works like
  `:htmx:`)
- HTMX accepts e.g `after-request` as an alternative to camelCase
  `afterRequest`