// Interim shared access: token lives only in this page's memory, never in a URL,
// cookie or browser storage. All holders share the same server-side data.
(() => {
  const originalFetch = window.fetch.bind(window);
  let token = "";
  let pending;

  function askToken() {
    if (pending) return pending;
    pending = new Promise(resolve => {
      const dialog = document.createElement("dialog");
      const form = document.createElement("form");
      form.method = "dialog";
      const heading = document.createElement("h2");
      heading.textContent = "Shared workspace access";
      const notice = document.createElement("p");
      notice.textContent = "Enter the access token from the operator. Everyone with this token shares the same files. Use throwaway public projects only.";
      const label = document.createElement("label");
      label.textContent = "Access token ";
      const input = document.createElement("input");
      input.type = "password";
      input.autocomplete = "off";
      input.required = true;
      input.maxLength = 512;
      label.append(input);
      const submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Continue";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Cancel";
      form.append(heading, notice, label, submit, cancel);
      dialog.append(form);
      document.body.append(dialog);
      let value = "";
      form.addEventListener("submit", () => { value = input.value; });
      cancel.addEventListener("click", () => dialog.close());
      dialog.addEventListener("close", () => {
        input.value = "";
        dialog.remove();
        resolve(value);
      }, {once: true});
      dialog.showModal();
      input.focus();
    }).finally(() => { pending = undefined; });
    return pending;
  }

  window.fetch = async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    if (url.origin !== window.location.origin || !/^\/(v1|artifacts)\//.test(url.pathname)) {
      return originalFetch(request);
    }
    const send = value => {
      const headers = new Headers(request.headers);
      if (value) headers.set("Authorization", `Bearer ${value}`);
      return originalFetch(new Request(request.clone(), {headers}));
    };
    let response = await send(token);
    if (response.status === 401) {
      token = await askToken();
      if (token) response = await send(token);
    }
    return response;
  };
})();
