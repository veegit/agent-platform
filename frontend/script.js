// script.js
const agentSelect    = document.getElementById('agentSelect');
const startBtn       = document.getElementById('startBtn');
const userIdInput    = document.getElementById('userId');
const initScreen     = document.getElementById('init-screen');
const chatScreen     = document.getElementById('chat-screen');
const messagesDiv    = document.getElementById('messages');
const messageInput   = document.getElementById('messageInput');
const sendBtn        = document.getElementById('sendBtn');
const spinner        = document.getElementById('spinner');
const agentNameSpan  = document.getElementById('agentName');

let conversationId    = null;
let currentUserId     = null;
let currentAgentId    = null;
let currentAgentName  = null;

// 1) Load agents (response: { agents: [ { agent_id, config: { persona: { name, … }}, … }, … ] })
fetch(CONFIG.LIFECYCLE_URL + '/agents')
  .then(res => res.json())
  .then(data => {
    data.agents.forEach(agent => {
      const opt = document.createElement('option');
      opt.value = agent.agent_id;
      opt.textContent = agent.config.persona.name;
      if (agent.status === 'active') {
        agentSelect.appendChild(opt);
      }
    });
  })
  .catch(err => console.error('Failed to load agents', err));

// 2) Start a new conversation
startBtn.addEventListener('click', () => {
  currentUserId    = userIdInput.value.trim();
  currentAgentId   = agentSelect.value;
  currentAgentName = agentSelect.selectedOptions[0].text;

  if (!currentUserId || !currentAgentId) {
    return alert('Enter user ID and select agent');
  }

  spinner.classList.remove('hidden');
  sendBtn.disabled = true;

  fetch(CONFIG.API_URL + '/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: currentUserId,
      agent_id: currentAgentId,
      initial_message: 'Hello'
    }),
  })
    .then(res => res.json())
    .then(data => {
      conversationId = data.id;
      initScreen.classList.add('hidden');
      chatScreen.classList.remove('hidden');
      agentNameSpan.textContent = currentAgentName;

      // initial reply is in data.last_message.content
      const text = data.last_message?.content || '';
      appendMessage(currentAgentName, text);
    })
    .catch(err => console.error(err))
    .finally(() => {
      spinner.classList.add('hidden');
      sendBtn.disabled = false;
    });
});

// 3) Send subsequent messages
sendBtn.addEventListener('click', () => {
  const content = messageInput.value.trim();
  if (!content) return;

  appendMessage('You', content);
  messageInput.value = '';
  spinner.classList.remove('hidden');
  sendBtn.disabled = true;

  fetch(CONFIG.API_URL + `/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: currentUserId,
      content: content
    })
  })
    .then(res => res.json())
    .then(data => {
      // agent reply is in data.message.content
      const msg = data.message;
      appendMessage(currentAgentName, msg.content);
    })
    .catch(err => console.error(err))
    .finally(() => {
      spinner.classList.add('hidden');
      sendBtn.disabled = false;
    });
});

// 4) Helper to render chat messages
function appendMessage(sender, text) {
  const msg = document.createElement('div');
  msg.classList.add('message');
  if (sender === 'You') msg.classList.add('user');
  msg.textContent = `${sender}: ${text}`;
  messagesDiv.appendChild(msg);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}
