const api = async (path, options = {}) => {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch (_) { /* response was not JSON */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
};

const formBody = (form) => new URLSearchParams(new FormData(form));
const money = (value) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value);

const bookCard = (book, score, editable = false) => {
  const article = document.createElement("article");
  article.className = "book";
  article.innerHTML = `<h3></h3><p class="author"></p><p class="category"></p><p class="price"></p>`;
  article.querySelector("h3").textContent = book.name;
  article.querySelector(".author").textContent = book.author || "作者未知";
  article.querySelector(".category").textContent = book.category || "未分类";
  article.querySelector(".price").textContent = money(book.price);
  if (editable) {
    const label = document.createElement("label");
    label.textContent = "评分（1-5）";
    const input = document.createElement("input");
    input.type = "number"; input.min = "1"; input.max = "5"; input.step = "0.5";
    input.name = `rating-${book.bookId}`;
    label.append(input); article.append(label);
  } else if (score !== undefined) {
    const line = document.createElement("p");
    line.textContent = `评分：${Number(score).toFixed(2)}`;
    article.append(line);
  }
  return article;
};

const clearAndRender = (node, values, adapter) => {
  node.replaceChildren(...values.map(adapter));
  if (!values.length) node.textContent = "暂无数据";
};

const logout = async () => {
  await api("logout", { method: "POST" });
  location.href = "index.html";
};

const home = async () => {
  const booksNode = document.querySelector("#books");
  const accountNode = document.querySelector("#account");
  const loginPanel = document.querySelector("#login-panel");
  const saveButton = document.querySelector("#save-ratings");
  const recommendLink = document.querySelector("#recommend-link");
  const logoutButton = document.querySelector("#logout");
  let account = null;
  try { account = await api("sessionlogin"); } catch (_) { /* anonymous */ }

  const renderAccount = () => {
    const authenticated = Boolean(account);
    loginPanel.hidden = authenticated;
    saveButton.hidden = !authenticated;
    recommendLink.hidden = !authenticated;
    logoutButton.hidden = !authenticated;
    accountNode.textContent = authenticated ? `欢迎，${account.name}（${account.email}）` : "登录后可评分和查看推荐";
  };
  renderAccount();
  const books = await api("books?pageno=1");
  clearAndRender(booksNode, books, (book) => bookCard(book, undefined, Boolean(account)));

  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#login-message");
    try {
      account = await api("user", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: formBody(event.target) });
      message.textContent = "";
      renderAccount();
      clearAndRender(booksNode, books, (book) => bookCard(book, undefined, true));
    } catch (error) { message.textContent = error.message; }
  });

  document.querySelector("#rating-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#rating-message");
    const values = [...event.target.querySelectorAll("input[type=number]")]
      .filter((input) => input.value)
      .map((input) => `${input.name.slice("rating-".length)}-${input.value}`);
    if (!values.length) { message.textContent = "请至少填写一本书的评分"; return; }
    try {
      const body = new URLSearchParams({ userId: account.userId, bookIdScores: values.join(",") });
      const result = await api("rating", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
      message.textContent = `已保存 ${result.recorded} 条评分`;
    } catch (error) { message.textContent = error.message; }
  });
  logoutButton.addEventListener("click", logout);
};

const register = () => {
  document.querySelector("#register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.querySelector("#register-message");
    try {
      await api("register", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: formBody(event.target) });
      location.href = "index.html";
    } catch (error) { message.textContent = error.message; }
  });
};

const recommendationPage = async () => {
  const message = document.querySelector("#recommendation-message");
  try {
    const account = await api("sessionlogin");
    const [purchased, recommended] = await Promise.all([
      api(`booklist?userId=${account.userId}`),
      api(`chinapub?userId=${account.userId}&format=json`)
    ]);
    clearAndRender(document.querySelector("#purchased"), purchased, (value) => bookCard(value.book, value.score));
    clearAndRender(document.querySelector("#recommended"), recommended, (value) => bookCard(value.book, value.score));
  } catch (error) {
    message.textContent = error.message;
    if (error.message.startsWith("401")) setTimeout(() => { location.href = "index.html"; }, 800);
  }
  document.querySelector("#logout").addEventListener("click", logout);
};

const page = document.body.dataset.page;
if (page === "home") home().catch((error) => { document.querySelector("#login-message").textContent = error.message; });
if (page === "register") register();
if (page === "recommendations") recommendationPage();
