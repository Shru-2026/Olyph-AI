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
  const SURVEY_FOLLOWUP_DELAY_MS = 0 * 60 * 1000; // 2 minutes
  const SURVEY_BUTTON_LIFETIME_MS = 0 * 60 * 1000; // 5 minutes lifetime for buttons

  // Replace this with your real support number and contact page
  const SUPPORT_CONTACT_NUMBER = "+91-77700 04323";
  const SUPPORT_CONTACT_LINK = "https://olyphaunt.com/contact-us/";

  // -------------------------
  // Utility: escape HTML to avoid XSS, except we'll insert safe links later
  // -------------------------
  function escapeHtml(unsafe) {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // -------------------------
  // addMessage: renders messages and converts URLs into clickable links
  // -------------------------
  function addMessage(content, sender = "bot") {
    const message = document.createElement("div");
    message.classList.add(sender === "bot" ? "bot-message" : "user-message");

    // Convert content to string
    let text = typeof content === "string" ? content : String(content);

    // Escape HTML to avoid XSS, then convert URLs to links
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    // First escape
    let escaped = escapeHtml(text);
    // Then replace escaped URLs with anchor tags (anchors themselves will be safe)
    const html = escaped.replace(urlRegex, (url) => {
      // url was escaped, so we need to unescape the visible url text for link label
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

  // -------------------------
  // Quick buttons helper (Yes / No)
  // -------------------------
  function addQuickButtons(id, buttonsConfig) {
    // don't add duplicate button sets
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
        // remove button group
        const el = document.getElementById(`quick-btns-${id}`);
        if (el) el.remove();
        // simulate user message in chat
        addMessage(b.label, "user");
        // handle the followup answer
        onSurveyFollowup(b.value);
      });
      container.appendChild(btn);
    });

    chatBody.appendChild(container);
    scrollChatToBottom();

    // Auto-remove after lifetime
    setTimeout(() => {
      const el = document.getElementById(`quick-btns-${id}`);
      if (el) el.remove();
    }, SURVEY_BUTTON_LIFETIME_MS);
  }

  // -------------------------
  // Survey follow-up handler
  // -------------------------
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
        // include both phone and clickable contact page link
        addMessage(
          `📞 No problem — if you need assistance, reach us at: ${SUPPORT_CONTACT_NUMBER}\n\n` +
            `🌐 You can also contact us here: ${SUPPORT_CONTACT_LINK}`,
          "bot"
        );
      }, 500);
    }
  }

  // -------------------------
  // Main flow: selection handling
  // -------------------------
  function handleSelection(option) {
    if (optionSelected) return;
    if (!sanityCheck(option)) return addMessage("⚠️ Invalid option selected!", "bot");

    optionSelected = true;
    selectedMode = option;

    // Hide the buttons
    if (buttonContainer) buttonContainer.style.display = "none";

    // Show the Home button
    if (homeButton) homeButton.style.display = "inline-block";

    if (option === "ask") {
      addMessage("Thank you for choosing Ask me anything. Connecting you with Olyph AI...", "bot");
      setTimeout(() => {
        addMessage("💬 Olyph AI is online! You can now ask about Olyphaunt Solutions or healthcare.", "bot");
      }, 1000);
    } else if (option === "survey") {
      addMessage("Thank you for choosing Survey Agent! Opening the form now...", "bot");

      // Open the Google Form after a short delay
      setTimeout(() => {
        window.open("https://forms.gle/u4pRVf1bAWSbWJA7A", "_blank");
      }, 1000);

      // Reset state and start follow-up timer
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
      addMessage("Thank you for choosing Report Agent. Connecting to reporting assistant...", "bot");
    }
  }

  // -------------------------
  // Conversational agent call (backend)
  // -------------------------
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

  // -------------------------
  // Sending messages (send button or Enter)
  // -------------------------
  async function handleSend() {
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = "";

    // If survey follow-up awaiting and user typed a quick answer, accept "yes"/"no"
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

  // -------------------------
  // Event listeners
  // -------------------------
  if (sendBtn) sendBtn.addEventListener("click", handleSend);

  if (userInput) {
    userInput.addEventListener("keypress", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault(); // Prevent newline
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

  // -------------------------
  // Reset chat
  // -------------------------
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

  // Initialize chat on load
  resetChat();
});
