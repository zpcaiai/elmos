# 只差注解就能转的函数（逐条已验证）

每一条的 `accepted` 都是**真的把补好注解的版本喂给分析器、它返回 READY**，
不是推断。两个都被接受时两个都列出来——那是两个不同的程序，选哪个是作者的事。

- 检查的候选：1469
- **只差注解（已验证）：5**（唯一解 0，多解 5）
- 补完注解仍被别的东西挡住：577
- 已标注但类型不在规范四类：616
- 槽位太多没搜（> 3）：162

## 待办

### `sortedcontainers-2.4.0/sortedcontainers/sortedlist.py:1686` — `identity`

```python
def identity(value)
```

- 加上 `value: int`, `-> int` → 引擎接受
- 加上 `value: int`, `-> float` → 引擎接受
- 加上 `value: float`, `-> float` → 引擎接受
- 加上 `value: bool`, `-> bool` → 引擎接受
- 加上 `value: str`, `-> str` → 引擎接受
- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断

### `mpmath-1.4.1/mpmath/libmp/libmpi.py:29` — `mpi_eq`

```python
def mpi_eq(s, t)
```

- 加上 `s: int`, `t: int`, `-> bool` → 引擎接受
- 加上 `s: int`, `t: float`, `-> bool` → 引擎接受
- 加上 `s: float`, `t: int`, `-> bool` → 引擎接受
- 加上 `s: float`, `t: float`, `-> bool` → 引擎接受
- 加上 `s: bool`, `t: bool`, `-> bool` → 引擎接受
- 加上 `s: str`, `t: str`, `-> bool` → 引擎接受
- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断

### `mpmath-1.4.1/mpmath/libmp/libmpi.py:32` — `mpi_ne`

```python
def mpi_ne(s, t)
```

- 加上 `s: int`, `t: int`, `-> bool` → 引擎接受
- 加上 `s: int`, `t: float`, `-> bool` → 引擎接受
- 加上 `s: float`, `t: int`, `-> bool` → 引擎接受
- 加上 `s: float`, `t: float`, `-> bool` → 引擎接受
- 加上 `s: bool`, `t: bool`, `-> bool` → 引擎接受
- 加上 `s: str`, `t: str`, `-> bool` → 引擎接受
- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断

### `tabulate-0.10.0/tabulate/__init__.py:209` — `_html_begin_table_without_header`

```python
def _html_begin_table_without_header(colwidths_ignore, colaligns_ignore)
```

- 加上 `colwidths_ignore: int`, `colaligns_ignore: int`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: int`, `colaligns_ignore: float`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: int`, `colaligns_ignore: bool`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: int`, `colaligns_ignore: str`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: float`, `colaligns_ignore: int`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: float`, `colaligns_ignore: float`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: float`, `colaligns_ignore: bool`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: float`, `colaligns_ignore: str`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: bool`, `colaligns_ignore: int`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: bool`, `colaligns_ignore: float`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: bool`, `colaligns_ignore: bool`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: bool`, `colaligns_ignore: str`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: str`, `colaligns_ignore: int`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: str`, `colaligns_ignore: float`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: str`, `colaligns_ignore: bool`, `-> str` → 引擎接受
- 加上 `colwidths_ignore: str`, `colaligns_ignore: str`, `-> str` → 引擎接受
- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断

### `tabulate-0.10.0/tabulate/__init__.py:1100` — `_padnone`

```python
def _padnone(ignore_width, s)
```

- 加上 `ignore_width: int`, `s: int`, `-> int` → 引擎接受
- 加上 `ignore_width: int`, `s: int`, `-> float` → 引擎接受
- 加上 `ignore_width: int`, `s: float`, `-> float` → 引擎接受
- 加上 `ignore_width: int`, `s: bool`, `-> bool` → 引擎接受
- 加上 `ignore_width: int`, `s: str`, `-> str` → 引擎接受
- 加上 `ignore_width: float`, `s: int`, `-> int` → 引擎接受
- 加上 `ignore_width: float`, `s: int`, `-> float` → 引擎接受
- 加上 `ignore_width: float`, `s: float`, `-> float` → 引擎接受
- 加上 `ignore_width: float`, `s: bool`, `-> bool` → 引擎接受
- 加上 `ignore_width: float`, `s: str`, `-> str` → 引擎接受
- 加上 `ignore_width: bool`, `s: int`, `-> int` → 引擎接受
- 加上 `ignore_width: bool`, `s: int`, `-> float` → 引擎接受
- 加上 `ignore_width: bool`, `s: float`, `-> float` → 引擎接受
- 加上 `ignore_width: bool`, `s: bool`, `-> bool` → 引擎接受
- 加上 `ignore_width: bool`, `s: str`, `-> str` → 引擎接受
- 加上 `ignore_width: str`, `s: int`, `-> int` → 引擎接受
- 加上 `ignore_width: str`, `s: int`, `-> float` → 引擎接受
- 加上 `ignore_width: str`, `s: float`, `-> float` → 引擎接受
- 加上 `ignore_width: str`, `s: bool`, `-> bool` → 引擎接受
- 加上 `ignore_width: str`, `s: str`, `-> str` → 引擎接受
- ⚠️ 多个赋值都被接受，它们**不是同一个程序**，需要作者判断
