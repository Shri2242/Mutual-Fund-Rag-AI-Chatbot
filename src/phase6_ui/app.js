document.addEventListener('DOMContentLoaded', () => {
  const chatForm = document.getElementById('chat-form');
  const queryInput = document.getElementById('query-input');
  const chatHistory = document.getElementById('chat-history');
  const sendBtn = document.getElementById('send-btn');
  const emptyState = document.getElementById('empty-state');
  const clearChatBtn = document.getElementById('clear-chat-btn');
  
  // Handle sidebar example questions
  const sidebarExamples = document.getElementById('sidebar-examples');
  if (sidebarExamples) {
    sidebarExamples.addEventListener('click', (e) => {
      if (e.target.tagName === 'LI') {
        // Strip quotes
        let text = e.target.textContent;
        if (text.startsWith('"') && text.endsWith('"')) {
          text = text.slice(1, -1);
        }
        queryInput.value = text;
        queryInput.focus();
      }
    });
  }

  // Handle Clear Chat
  clearChatBtn.addEventListener('click', () => {
    chatHistory.innerHTML = '';
    chatHistory.style.display = 'none';
    emptyState.style.display = 'flex';
    queryInput.value = '';
    queryInput.focus();
  });

  // Handle Form Submission
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;

    // Hide empty state and show chat on EVERY query submission
    emptyState.style.display = 'none';
    chatHistory.style.display = 'flex';

    // Add user message
    appendUserMessage(query);
    queryInput.value = '';
    sendBtn.disabled = true;

    // Add typing indicator
    const typingId = appendTypingIndicator();

    try {
      // Call the backend API
      const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
      });

      const data = await response.json();
      
      // Remove typing indicator
      document.getElementById(typingId)?.remove();

      if (response.ok) {
        appendAIMessage(data);
      } else {
        appendAIErrorMessage(data.detail || 'An error occurred.');
      }
    } catch (error) {
      document.getElementById(typingId)?.remove();
      appendAIErrorMessage('Failed to connect to the server.');
      console.error(error);
    } finally {
      sendBtn.disabled = false;
      queryInput.focus();
    }
  });

  function appendUserMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message user-message';
    msgDiv.textContent = text;
    chatHistory.appendChild(msgDiv);
    scrollToBottom();
  }

  function appendTypingIndicator() {
    const id = 'typing-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.id = id;
    msgDiv.className = 'message ai-message-wrapper';
    msgDiv.innerHTML = `
      <div class="ai-avatar">
        <i data-feather="box"></i>
      </div>
      <div class="ai-message">
        <div class="message-body">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    `;
    chatHistory.appendChild(msgDiv);
    feather.replace();
    scrollToBottom();
    return id;
  }

  function appendAIMessage(data) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message ai-message-wrapper';
    
    let sourceHtml = '';
    if (data.source_url) {
      sourceHtml = `
        <div class="source-block">
          <span class="source-label">Sources</span>
          <a href="${data.source_url}" target="_blank" rel="noopener noreferrer" class="source-link">
            <i data-feather="link-2"></i> groww.in/mutual-funds
          </a>
          <div class="source-footer">
            <i data-feather="check-circle" style="color: var(--primary-color);"></i>
            Verified from 1 source
          </div>
        </div>
      `;
    }

    // We need to append actions to the container
    const containerDiv = document.createElement('div');
    containerDiv.style.width = '100%';
    containerDiv.innerHTML = `
      <div class="ai-message">
        <div class="message-header">
          <i data-feather="check-circle" style="width: 14px; height: 14px; color: var(--primary-color);"></i>
          <span class="msg-title">Verified Answer</span>
        </div>
        <div class="message-body">
          <p>${(data.answer_body || '').replace(/\n/g, '<br>')}</p>
        </div>
        ${sourceHtml}
      </div>
    `;
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';
    actionsDiv.innerHTML = `
      <button><i data-feather="thumbs-up"></i></button>
      <button><i data-feather="thumbs-down"></i></button>
    `;
    containerDiv.appendChild(actionsDiv);
    
    // Reset wrapper
    msgDiv.innerHTML = `
      <div class="ai-avatar">
        <i data-feather="box"></i>
      </div>
    `;
    msgDiv.appendChild(containerDiv);

    chatHistory.appendChild(msgDiv);
    feather.replace();
    scrollToBottom();
  }

  function appendAIErrorMessage(errorMsg) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message ai-message-wrapper';
    msgDiv.innerHTML = `
      <div class="ai-avatar">
        <i data-feather="alert-triangle" style="color: var(--danger);"></i>
      </div>
      <div class="ai-message" style="border-color: rgba(255,82,82,0.3);">
        <div class="message-header">
          <i data-feather="alert-circle" style="width: 14px; height: 14px; color: var(--danger);"></i>
          <span class="msg-title" style="color: var(--danger);">ERROR</span>
        </div>
        <div class="message-body">
          <p>${errorMsg}</p>
        </div>
      </div>
    `;
    chatHistory.appendChild(msgDiv);
    feather.replace();
    scrollToBottom();
  }

  function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
  }
});
