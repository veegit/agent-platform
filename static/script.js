document.addEventListener('DOMContentLoaded', () => {
    const userIdInput = document.getElementById('userId');
    const agentIdSelect = document.getElementById('agentId');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const chatbox = document.getElementById('chatbox');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const initialSetupDiv = document.getElementById('initialSetup');
    const conversationDisplayDiv = document.getElementById('conversationDisplay');
    const displayUserIdSpan = document.getElementById('displayUserId');
    const displayAgentNameSpan = document.getElementById('displayAgentName');

    let currentConversationId = null;
    let currentUserId = '';
    let currentAgentName = '';
    let agents = []; // To store agent details

    // --- Helper function to add messages to the chatbox ---
    function addMessageToChatbox(message, role) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', role + '-message');
        messageDiv.textContent = message;
        chatbox.appendChild(messageDiv);
        chatbox.scrollTop = chatbox.scrollHeight; // Scroll to bottom
    }

    // --- Fetch Agents and Populate Dropdown ---
    async function fetchAgents() {
        try {
            const response = await fetch('http://localhost:8003/agents'); // Assuming API is served from the same origin
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            agents = data.agents || []; // Store agents
            agentIdSelect.innerHTML = '<option value="">Select an Agent</option>'; // Clear loading/default
            if (agents.length > 0) {
                agents.forEach(agent => {
                    const option = document.createElement('option');
                    option.value = agent.agent_id;
                    option.textContent = agent.name || agent.agent_id; // Use name, fallback to ID
                    agentIdSelect.appendChild(option);
                });
            } else {
                agentIdSelect.innerHTML = '<option value="">No agents available</option>';
            }
        } catch (error) {
            console.error('Error fetching agents:', error);
            agentIdSelect.innerHTML = '<option value="">Error loading agents</option>';
            addMessageToChatbox('Error loading agents. Please try refreshing.', 'system');
        }
    }

    // --- Toggle UI State (Loading/Idle) ---
    function setLoadingState(isLoading) {
        if (isLoading) {
            sendButton.disabled = true;
            messageInput.disabled = true;
            loadingIndicator.style.display = 'inline';
        } else {
            sendButton.disabled = false;
            messageInput.disabled = false;
            loadingIndicator.style.display = 'none';
        }
    }

    // --- Handle Send Button Click ---
    sendButton.addEventListener('click', async () => {
        const messageText = messageInput.value.trim();
        if (!messageText) return;

        currentUserId = userIdInput.value.trim();
        const selectedAgentId = agentIdSelect.value;

        if (!currentUserId) {
            addMessageToChatbox('Please enter a User ID.', 'system');
            return;
        }
        if (!selectedAgentId && !currentConversationId) {
             addMessageToChatbox('Please select an Agent.', 'system');
            return;
        }

        setLoadingState(true);
        addMessageToChatbox(messageText, 'user'); // Display user's message immediately

        if (!currentConversationId) {
            // --- Start a new conversation ---
            try {
                const selectedAgent = agents.find(agent => agent.agent_id === selectedAgentId);
                currentAgentName = selectedAgent ? (selectedAgent.name || selectedAgentId) : selectedAgentId;

                const response = await fetch('/conversations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        agent_id: selectedAgentId,
                        user_id: currentUserId,
                        initial_message: messageText
                    })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: 'Failed to start conversation. Please check server logs.' }));
                    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
                }
                const conversationData = await response.json();
                currentConversationId = conversationData.id;

                // Display conversation info and switch views
                displayUserIdSpan.textContent = currentUserId;
                displayAgentNameSpan.textContent = currentAgentName;
                initialSetupDiv.style.display = 'none';
                conversationDisplayDiv.style.display = 'block';


                if (conversationData.last_message && conversationData.last_message.content) {
                    addMessageToChatbox(conversationData.last_message.content, 'agent');
                } else {
                    // If there was an issue and no explicit agent first message, give some feedback
                    addMessageToChatbox("Conversation started. Waiting for agent's response...", 'system');
                }

            } catch (error) {
                console.error('Error starting conversation:', error);
                addMessageToChatbox(`Error: ${error.message}`, 'system');
                // Rollback optimistic user message display if start conversation fails
                chatbox.removeChild(chatbox.lastChild);
            }
        } else {
            // --- Send a subsequent message ---
            try {
                const response = await fetch(`/conversations/${currentConversationId}/messages`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content: messageText,
                        user_id: currentUserId // Assuming API requires userId for subsequent messages too
                    })
                });
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: 'Failed to send message. Please check server logs.' }));
                    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
                }
                const messageData = await response.json();
                if (messageData.message && messageData.message.content) {
                    addMessageToChatbox(messageData.message.content, 'agent');
                }
            } catch (error) {
                console.error('Error sending message:', error);
                addMessageToChatbox(`Error: ${error.message}`, 'system');
                // Rollback optimistic user message display if send message fails
                chatbox.removeChild(chatbox.lastChild);
            }
        }

        messageInput.value = ''; // Clear input field
        setLoadingState(false);
        messageInput.focus();
    });

    // --- Initial Load ---
    fetchAgents();
});
