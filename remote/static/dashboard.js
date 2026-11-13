"use strict";
const byId = id => document.getElementById(id);
let token = sessionStorage.getItem("bellalun-remote-token") || "";
let logJob = null;
async function api(path, data) {
  const response = await fetch(path, {method: data === undefined ? "GET" : "POST",
    headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data), cache: "no-store"});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "서버 요청 실패");
  return value;
}
function message(value) { byId("message").textContent = value; }
function optionList(id, rows, label) {
  const select = byId(id), previous = select.value;
  select.replaceChildren(new Option("선택하세요", ""));
  for (const row of rows) select.add(new Option(label(row), row.id));
  select.value = previous;
}
function button(label, action, disabled = false) {
  const node = document.createElement("button"); node.type = "button";
  node.textContent = label; node.disabled = disabled;
  node.addEventListener("click", () => Promise.resolve(action()).catch(error => message(error.message)));
  return node;
}
async function download(job) {
  const value = await api("/jobs/" + job.id + "/results");
  const bytes = Uint8Array.from(atob(value.package), char => char.charCodeAt(0));
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
    .map(byte => byte.toString(16).padStart(2, "0")).join("");
  if (digest !== value.package_sha256) throw new Error("다운로드 ZIP 해시 불일치");
  const url = URL.createObjectURL(new Blob([bytes], {type: "application/zip"}));
  const link = document.createElement("a"); link.href = url;
  link.download = job.id + "-" + value.bundle_id + ".zip"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  message("전송 ZIP 해시 확인 완료. 오프라인 링크는 압축 해제한 view/Reports에서 확인하세요.");
}
async function refresh() {
  if (!token) return;
  const authenticatedToken = token;
  const [catalog, records] = await Promise.all([api("/catalog"), api("/jobs")]);
  if (!token || authenticatedToken !== token) return;
  optionList("pc", catalog.pcs.filter(pc => pc.enabled), pc => pc.id + (pc.shared_interlock ? " · 공용 잠금" : " · 잠금 준비 확인 필요"));
  optionList("profile", catalog.profiles, row => row.id);
  optionList("bundle", catalog.bundles.map(id => ({id})), row => row.id);
  byId("controls").hidden = false;
  byId("connection").textContent = "인증된 서버에 연결되었습니다.";
  const body = byId("jobs"); body.replaceChildren();
  for (const job of records.jobs) {
    const row = document.createElement("tr");
    for (const value of [job.id.slice(0, 12), job.pc_id + " / " + job.profile_id, job.status,
      job.engine_run_id ? "엔진 " + job.engine_run_id + " · 종료 " + job.exit_code : "엔진 완료 미확인"]) {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    }
    const actions = document.createElement("td");
    actions.append(button("로그", async () => { logJob = job.id; byId("logs").textContent = (await api("/jobs/" + job.id + "/logs")).log || "기록 없음"; }));
    actions.append(button("취소", async () => { await api("/jobs/" + job.id + "/cancel", {}); await refresh(); },
      !["queued", "running", "cancelling", "uncertain"].includes(job.status)));
    actions.append(button("결과 ZIP", () => download(job), !job.result_bundle_id));
    row.append(actions); body.append(row);
  }
  if (logJob) byId("logs").textContent = (await api("/jobs/" + logJob + "/logs")).log || "기록 없음";
}
byId("auth").addEventListener("submit", async event => {
  event.preventDefault(); token = byId("token").value; byId("token").value = "";
  try { await refresh(); sessionStorage.setItem("bellalun-remote-token", token); message(""); }
  catch (error) { token = ""; sessionStorage.removeItem("bellalun-remote-token");
    byId("controls").hidden = true; byId("jobs").replaceChildren(); message(error.message); }
});
byId("logout").addEventListener("click", () => {
  token = ""; logJob = null; sessionStorage.removeItem("bellalun-remote-token");
  byId("controls").hidden = true; byId("jobs").replaceChildren(); byId("logs").textContent = "연결 해제";
  byId("connection").textContent = "접근 토큰을 입력하세요.";
});
byId("submit").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const job = await api("/jobs", {pc_id: byId("pc").value, profile_id: byId("profile").value,
      bundle_id: byId("bundle").value, restore_after: byId("restore").value === "true"});
    message("실행 요청 " + job.id); await refresh();
  } catch (error) { message(error.message); }
});
byId("refresh").addEventListener("click", () => refresh().catch(error => message(error.message)));
setInterval(() => refresh().catch(error => message(error.message)), 3000);
refresh().catch(error => message(error.message));
