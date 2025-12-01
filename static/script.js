// static/script.js
document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Olyph AI script loaded successfully");

  const chatBody = document.getElementById("chat-body");
  const buttonContainer = document.querySelector(".button-container");
  const homeButton = document.getElementById("homeBtn");
  const sendBtn = document.getElementById("sendBtn");
  const userInput = document.getElementById("userInput");

  let optionSelected = false;
  let selectedMode = null;

  // Survey follow-up state
  let surveyFollowupTimer = null;
  let surveyFollowupAnswered = false;
  const SURVEY_FOLLOWUP_ID = "survey-fill-check";
  const SURVEY_FOLLOWUP_DELAY_MS = 2 * 60 * 1000; // 2 minutes
  const SURVEY_BUTTON_LIFETIME_MS = 5 * 60 * 1000; // 5 minutes lifetime for buttons

  // Replace this with your real support number and contact page
  const SUPPORT_CONTACT_NUMBER = "+91-77700 04323";
  const SUPPORT_CONTACT_LINK = "https://olyphaunt.com/contact-us/";

  function escapeHtml(unsafe) {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function addMessage(content, sender = "bot") {
    const message = document.createElement("div");
    message.classList.add(sender === "bot" ? "bot-message" : "user-message");

    let text = typeof content === "string" ? content : String(content);
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    let escaped = escapeHtml(text);
    const html = escaped.replace(urlRegex, (url) => {
      const visible = escapeHtml(url);
      return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-link">${visible}</a>`;
    });

    message.innerHTML = html;
    chatBody.appendChild(message);
    scrollChatToBottom();
  }

  function scrollChatToBottom() {
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  function sanityCheck(option) {
    const validOptions = ["ask", "survey", "report"];
    return validOptions.includes(option);
  }

  function addQuickButtons(id, buttonsConfig) {
    if (document.getElementById(`quick-btns-${id}`)) return;

    const container = document.createElement("div");
    container.id = `quick-btns-${id}`;
    container.className = "quick-btns";

    buttonsConfig.forEach((b) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quick-btn";
      btn.innerText = b.label;
      btn.dataset.value = b.value;
      btn.addEventListener("click", () => {
        const el = document.getElementById(`quick-btns-${id}`);
        if (el) el.remove();
        addMessage(b.label, "user");
        onSurveyFollowup(b.value);
      });
      container.appendChild(btn);
    });

    chatBody.appendChild(container);
    scrollChatToBottom();

    setTimeout(() => {
      const el = document.getElementById(`quick-btns-${id}`);
      if (el) el.remove();
    }, SURVEY_BUTTON_LIFETIME_MS);
  }

  function onSurveyFollowup(value) {
    if (surveyFollowupAnswered) return;
    surveyFollowupAnswered = true;

    if (surveyFollowupTimer) {
      clearTimeout(surveyFollowupTimer);
      surveyFollowupTimer = null;
    }

    if (value === "yes") {
      setTimeout(() => {
        addMessage("✅ Thank you for filling the form! We appreciate your time.", "bot");
      }, 500);
    } else if (value === "no") {
      setTimeout(() => {
        addMessage(
          `📞 No problem — if you need assistance, reach us at: ${SUPPORT_CONTACT_NUMBER}\n\n` +
            `🌐 You can also contact us here: ${SUPPORT_CONTACT_LINK}`,
          "bot"
        );
      }, 500);
    }
  }

  /* ------------------ UI helpers ------------------ */

  // Makes main buttons visible and hides home
  function showMainMenu() {
    if (buttonContainer) buttonContainer.style.display = "flex";
    if (homeButton) homeButton.style.display = "none";
    optionSelected = false;
    selectedMode = null;
  }

  // Hides main menu; leaves home button visible (used after download success)
  function hideMainMenuKeepHome() {
    if (buttonContainer) buttonContainer.style.display = "none";
    if (homeButton) homeButton.style.display = "inline-block";
    optionSelected = true; // prevent reactivation until user uses home
    selectedMode = null;
  }

  // Reset chat to greeting and show main menu (use when clicking Home)
  function resetChat() {
    if (surveyFollowupTimer) {
      clearTimeout(surveyFollowupTimer);
      surveyFollowupTimer = null;
    }
    surveyFollowupAnswered = false;

    if (chatBody) chatBody.innerHTML = "";
    addMessage("👋 Greetings, this is OlyphAI. How can I help you?");
    if (buttonContainer) buttonContainer.style.display = "flex";
    if (homeButton) homeButton.style.display = "none";
    optionSelected = false;
    selectedMode = null;
  }

  /* ------------------ Credential Modal ------------------ */
  function createCredentialModal(defaultFormat = "csv") {
    if (document.getElementById("cred-modal")) return null;

    const overlay = document.createElement("div");
    overlay.id = "cred-modal-overlay";
    overlay.style = `
      position: fixed; inset: 0; background: rgba(0,0,0,0.4); display:flex;
      align-items:center; justify-content:center; z-index:9999;
    `;

    const modal = document.createElement("div");
    modal.id = "cred-modal";
    modal.style = `
      width: 320px; background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 6px 24px rgba(0,0,0,0.2);
      font-family: inherit;
    `;

    modal.innerHTML = `
      <h3 style="margin:0 0 8px 0; font-size:18px; color:#002b5c;">Report Download - Authenticate</h3>
      <label style="display:block; margin-top:8px; font-weight:600;">Username</label>
      <input id="cred-username" type="text" placeholder="Username" style="width:100%; padding:8px; margin-top:6px; border-radius:6px; border:1px solid #ddd;" />
      <label style="display:block; margin-top:10px; font-weight:600;">Password</label>
      <input id="cred-password" type="password" placeholder="Password" style="width:100%; padding:8px; margin-top:6px; border-radius:6px; border:1px solid #ddd;" />
      <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:14px;">
        <button id="cred-cancel-btn" style="padding:8px 12px; border-radius:6px; border:none; background:#ccc; cursor:pointer;">Cancel</button>
        <button id="cred-submit-btn" style="padding:8px 12px; border-radius:6px; border:none; background:#0078ff; color:white; cursor:pointer;">Download</button>
      </div>
      <div id="cred-error" style="color:#b00020; margin-top:8px; display:none; font-size:13px;"></div>
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const cancelBtn = document.getElementById("cred-cancel-btn");
    const submitBtn = document.getElementById("cred-submit-btn");
    const usernameInput = document.getElementById("cred-username");
    const passwordInput = document.getElementById("cred-password");
    const errorDiv = document.getElementById("cred-error");

    function closeModal() {
      overlay.remove();
    }

    cancelBtn.addEventListener("click", () => {
      closeModal();
      addMessage("Report cancelled.", "bot");
      showMainMenu();
    });

    passwordInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") submitBtn.click();
    });

    submitBtn.addEventListener("click", async () => {
      const username = usernameInput.value.trim();
      const password = passwordInput.value;
      if (!username || !password) {
        errorDiv.style.display = "block";
        errorDiv.innerText = "Please enter both username and password.";
        return;
      }
      errorDiv.style.display = "none";

      try {
        const fmt = defaultFormat || "csv";
        addMessage("Authenticating and requesting report...", "bot");

        const res = await fetch("/api/report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, format: fmt })
        });

        if (!res.ok) {
          const body = await res.json().catch(()=>({error: res.statusText}));
          errorDiv.style.display = "block";
          errorDiv.innerText = body.error || "Authentication failed or internal error.";
          return;
        }

        const disposition = res.headers.get("content-disposition") || "";
        let filename = fmt === "xlsx" ? "report.xlsx" : "report.csv";
        const match = disposition.match(/filename\*=UTF-8''(.+)|filename="?(.*?)"?(;|$)/);
        if (match) filename = decodeURIComponent(match[1] || match[2]);

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        closeModal();

        // final message instead of showing menu again
        addMessage("Thank you for reaching to us, the csv file is downloaded in your device", "bot");

        // hide main buttons but KEEP the Home button visible
        hideMainMenuKeepHome();

      } catch (err) {
        errorDiv.style.display = "block";
        errorDiv.innerText = "Request failed: " + (err.message || err);
      }
    });

    usernameInput.focus();
    return overlay;
  }

  /* ------------------ Main flow ------------------ */
  function handleSelection(option) {
    if (optionSelected) return;
    if (!sanityCheck(option)) return addMessage("⚠️ Invalid option selected!", "bot");

    optionSelected = true;
    selectedMode = option;

    if (buttonContainer) buttonContainer.style.display = "none";
    if (homeButton) homeButton.style.display = "inline-block";

    if (option === "ask") {
      addMessage("Thank you for choosing Ask me anything. Connecting you with Olyph AI...", "bot");
      setTimeout(() => {
        addMessage("💬 Olyph AI is online! You can now ask about Olyphaunt Solutions or healthcare.", "bot");
      }, 1000);
    } else if (option === "survey") {
      addMessage("Thank you for choosing Survey Agent! Opening the form now...", "bot");

      setTimeout(() => {
        window.open("https://forms.gle/u4pRVf1bAWSbWJA7A", "_blank");
      }, 1000);

      surveyFollowupAnswered = false;
      if (surveyFollowupTimer) {
        clearTimeout(surveyFollowupTimer);
      }
      surveyFollowupTimer = setTimeout(() => {
        if (surveyFollowupAnswered) return;
        addMessage("Did you fill the form we just opened? (Please choose an option below)", "bot");
        addQuickButtons(SURVEY_FOLLOWUP_ID, [
          { label: "Yes, I filled it", value: "yes" },
          { label: "No, I couldn't", value: "no" },
        ]);
      }, SURVEY_FOLLOWUP_DELAY_MS);
    } else if (option === "report") {
      addMessage("Thank you for choosing Report Agent. Opening authentication...", "bot");
      setTimeout(() => {
        createCredentialModal("csv");
      }, 300);
    }
  }

  /* ------------------ Conversational Agent ------------------ */
  async function callConversationalAgent(userMessage) {
    addMessage(userMessage, "user");

    try {
      const response = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });

      const data = await response.json();
      addMessage(data.reply, "bot");
    } catch (error) {
      addMessage("⚠️ Could not connect to Olyph AI server.", "bot");
      console.error(error);
    }
  }

  /* ------------------ Sending messages ------------------ */
  async function handleSend() {
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = "";

    if (selectedMode === "survey" && !surveyFollowupAnswered) {
      const lower = message.toLowerCase();
      if (lower === "yes" || lower === "y" || lower.includes("i filled")) {
        addMessage("Yes", "user");
        onSurveyFollowup("yes");
        return;
      } else if (lower === "no" || lower === "n" || lower.includes("couldn't") || lower.includes("could not")) {
        addMessage("No", "user");
        onSurveyFollowup("no");
        return;
      }
    }

    if (selectedMode === "ask") {
      await callConversationalAgent(message);
    } else {
      addMessage(message, "user");
      setTimeout(() => addMessage("We’ll get back to you soon.", "bot"), 500);
    }
  }

  /* ------------------ Event listeners ------------------ */
  if (sendBtn) sendBtn.addEventListener("click", handleSend);

  if (userInput) {
    userInput.addEventListener("keypress", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    });
  }

  const askBtn = document.getElementById("askBtn");
  const surveyBtn = document.getElementById("surveyBtn");
  const reportBtn = document.getElementById("reportBtn");

  if (askBtn) askBtn.addEventListener("click", () => handleSelection("ask"));
  if (surveyBtn) surveyBtn.addEventListener("click", () => handleSelection("survey"));
  if (reportBtn) reportBtn.addEventListener("click", () => handleSelection("report"));

  if (homeButton) {
    homeButton.addEventListener("click", () => {
      resetChat();
    });
  }

  // Initialize chat on load
  resetChat();
});
