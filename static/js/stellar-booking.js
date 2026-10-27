// Pay for a dorm booking from a Freighter wallet.
// The server builds the transaction, Freighter signs it, the server submits it.
(function () {
  const panel = document.getElementById("stellar-pay");
  if (!panel) return;

  const button = panel.querySelector("[data-stellar-pay]");
  const status = panel.querySelector("[data-stellar-status]");
  const csrfToken = panel.dataset.csrf;

  function show(message, kind) {
    status.textContent = message;
    status.className = "small mt-3 text-" + (kind || "light");
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  button.addEventListener("click", async function () {
    const freighter = window.freighterApi;
    button.disabled = true;
    try {
      if (!freighter || !(await freighter.isConnected()).isConnected) {
        throw new Error("Freighter wallet not found. Install it from freighter.app and try again.");
      }

      show("Connecting to your wallet…");
      const access = await freighter.requestAccess();
      if (access.error) throw new Error(access.error.message || access.error);
      const address = access.address;

      show("Preparing transaction…");
      const prepared = await post(panel.dataset.prepareUrl, { address: address });

      show("Approve the payment in Freighter…");
      const signed = await freighter.signTransaction(prepared.xdr, {
        networkPassphrase: panel.dataset.networkPassphrase,
        address: address,
      });
      if (signed.error) throw new Error(signed.error.message || signed.error);

      show("Submitting to the Stellar network…");
      const result = await post(panel.dataset.submitUrl, { address: address, signed_xdr: signed.signedTxXdr });
      show("Booking confirmed on-chain!", "success");
      window.location.href = result.redirect;
    } catch (err) {
      show(err.message || String(err), "warning");
      button.disabled = false;
    }
  });
})();
