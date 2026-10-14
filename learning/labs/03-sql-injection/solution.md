# Lab 03 solution

Use a bound parameter, never string formatting:

```python
rows = con.execute(
    "SELECT * FROM transactions WHERE description LIKE ? LIMIT 50",
    (f"%{q}%",),
).fetchall()
```

The `%` wildcards belong to the *value* you pass, not the SQL text. Re-push and
confirm both tools go quiet. Note that the route is behind `require_session`
(see `server/app.py`), so exploitation needs a session: severity is lower than
on an open route, but SQL injection is still a fix, not a suppression.
