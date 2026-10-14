"use strict";

// Fetch rejects relative addresses when the page URL contains userinfo.
// Capture that login in memory, then use clean absolute addresses for every API call.
function createMedPravoClient(pageAddress, fetchRequest, pageHistory) {
  const page = new URL(pageAddress);
  let authorization = null;
  if (page.username || page.password) {
    const pair = decodeURIComponent(page.username) + ":" + decodeURIComponent(page.password);
    authorization = "Basic " + btoa(String.fromCharCode(...new TextEncoder().encode(pair)));
    page.username = "";
    page.password = "";
    if (pageHistory) pageHistory.replaceState(null, "", page.href);
  }
  async function request(path, body) {
    const address = new URL("/api/" + path, page.origin);
    const headers = {"Content-Type":"application/json", "X-MedPravo-Request":"1"};
    if (authorization) headers.Authorization = authorization;
    const response = await fetchRequest(address.href, {
      method: body === undefined ? "GET" : "POST", headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin", cache: "no-store"
    });
    if (!response.ok) {
      let detail; try { detail = (await response.json()).error; } catch (_) {}
      throw Error(response.status === 401 ? "Требуется вход в кабинет. Обновите страницу и введите логин и пароль."
        : detail || "Ошибка запроса: " + response.status);
    }
    return response;
  };
  const client = async (path,body) => (await request(path,body)).json();
  client.download = async path => {
    const response = await request(path);
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    return {blob:await response.blob(),filename:match?decodeURIComponent(match[1]):"document"};
  };
  return client;
}
