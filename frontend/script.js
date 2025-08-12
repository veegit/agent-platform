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

// Store agent flow data for each message
let messageFlowData   = new Map();

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
      const agentFlow = data.last_message?.agent_flow || null;
      console.log('Initial message agent flow data:', agentFlow);
      appendMessage(currentAgentName, text, agentFlow);
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
      const agentFlow = msg.agent_flow || null;
      console.log('Message response agent flow data:', agentFlow);
      appendMessage(currentAgentName, msg.content, agentFlow);
    })
    .catch(err => console.error(err))
    .finally(() => {
      spinner.classList.add('hidden');
      sendBtn.disabled = false;
    });
});

// 4) Helper to render chat messages
function appendMessage(sender, text, agentFlow = null) {
  const msg = document.createElement('div');
  msg.classList.add('message');
  if (sender === 'You') msg.classList.add('user');
  
  // Create message content container
  const messageContent = document.createElement('div');
  messageContent.classList.add('message-content');
  
  // Handle different text formats
  let displayText = text;
  
  // Check if text is a JSON object (shouldn't happen after backend fix, but safety check)
  if (typeof text === 'object' && text !== null) {
    if (text.content) {
      displayText = text.content;
    } else {
      displayText = JSON.stringify(text);
    }
  }
  
  // Ensure displayText is a string
  if (typeof displayText !== 'string') {
    displayText = String(displayText);
  }
  
  // For user messages, just show plain text
  if (sender === 'You') {
    messageContent.textContent = `${sender}: ${displayText}`;
  } else {
    // For agent messages, render markdown
    const senderSpan = document.createElement('strong');
    senderSpan.textContent = `${sender}: `;
    messageContent.appendChild(senderSpan);
    
    const contentDiv = document.createElement('div');
    contentDiv.innerHTML = marked.parse(displayText);
    messageContent.appendChild(contentDiv);
  }
  
  msg.appendChild(messageContent);
  
  // Add info button for agent messages with flow data
  console.log('appendMessage called with:', { sender, hasAgentFlow: !!agentFlow, agentFlow });
  if (sender !== 'You' && agentFlow) {
    console.log('Creating info button for message with flow data');
    const infoBtn = document.createElement('button');
    infoBtn.classList.add('flow-info-btn');
    infoBtn.textContent = 'i';
    infoBtn.title = 'View Agent Flow Diagram';
    
    // Generate unique message ID and store flow data
    const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    messageFlowData.set(messageId, agentFlow);
    console.log('Stored flow data for message:', messageId);
    
    infoBtn.addEventListener('click', () => showFlowDiagram(messageId));
    msg.appendChild(infoBtn);
  } else {
    console.log('No info button created:', { isUser: sender === 'You', hasFlow: !!agentFlow });
  }
  
  messagesDiv.appendChild(msg);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// 5) Agent Flow Diagram Functions
function showFlowDiagram(messageId) {
  const flowData = messageFlowData.get(messageId);
  if (!flowData) {
    console.error('No flow data found for message:', messageId);
    return;
  }
  
  // Show modal
  const modal = document.getElementById('flowModal');
  modal.classList.remove('hidden');
  
  // Update modal title with flow information
  const modalTitle = modal.querySelector('.modal-header h3');
  const skillCount = flowData.nodes ? flowData.nodes.filter(n => n.type === 'skill').length : 0;
  const agentCount = flowData.nodes ? flowData.nodes.filter(n => n.type === 'agent').length : 0;
  modalTitle.textContent = `Agent Flow: ${agentCount} Agent(s), ${skillCount} Skill(s)`;
  
  // Clear previous diagram
  const diagramContainer = document.getElementById('flowDiagram');
  diagramContainer.innerHTML = '';
  
  // Create the diagram
  createFlowDiagram(diagramContainer, flowData);
}

function createFlowDiagram(container, flowData) {
  const width = container.clientWidth || 760;
  const height = container.clientHeight || 380;
  
  // Create SVG
  const svg = d3.select(container)
    .append('svg')
    .attr('width', width)
    .attr('height', height);
  
  // Define arrow marker
  svg.append('defs')
    .append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 8)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#666');
  
  // Process nodes and edges
  const nodes = flowData.nodes || [];
  const edges = flowData.edges || [];
  
  if (nodes.length === 0) {
    svg.append('text')
      .attr('x', width / 2)
      .attr('y', height / 2)
      .attr('text-anchor', 'middle')
      .attr('fill', '#666')
      .text('No flow data available');
    return;
  }
  
  // Calculate layout positions
  const nodePositions = calculateNodePositions(nodes, edges, width, height);
  
  // Draw edges first (so they appear behind nodes)
  edges.forEach(edge => {
    const fromPos = nodePositions[edge.from_node];
    const toPos = nodePositions[edge.to_node];
    
    if (fromPos && toPos) {
      // Draw edge line
      svg.append('line')
        .attr('class', 'flow-edge')
        .attr('x1', fromPos.x)
        .attr('y1', fromPos.y)
        .attr('x2', toPos.x)
        .attr('y2', toPos.y);
      
      // Add edge label if available
      if (edge.label) {
        const midX = (fromPos.x + toPos.x) / 2;
        const midY = (fromPos.y + toPos.y) / 2;
        
        // Determine edge type for better labeling
        let labelText = edge.label;
        const fromNode = nodes.find(n => n.id === edge.from_node);
        const toNode = nodes.find(n => n.id === edge.to_node);
        
        if (fromNode && toNode) {
          if (fromNode.type === 'agent' && toNode.type === 'skill') {
            labelText = 'uses skill';
          } else if (fromNode.type === 'reasoning' && toNode.type === 'skill') {
            labelText = 'executes';
          } else if (fromNode.type === 'delegation' && toNode.type === 'agent') {
            labelText = 'delegates to';
          }
        }
        
        svg.append('text')
          .attr('class', 'flow-edge-label')
          .attr('x', midX)
          .attr('y', midY - 5)
          .text(labelText);
      }
    }
  });
  
  // Draw nodes
  nodes.forEach(node => {
    const pos = nodePositions[node.id];
    if (!pos) return;
    
    const nodeGroup = svg.append('g')
      .attr('class', `flow-node ${node.type}`);
    
    // Calculate node dimensions based on type and content
    let rectWidth, rectHeight;
    let displayText = node.name;
    
    if (node.type === 'skill') {
      // Make skill nodes more prominent and add skill details
      const skillId = node.metadata?.skill_id || '';
      const skillStatus = node.metadata?.status || '';
      displayText = `${node.name}`;
      if (skillStatus) {
        displayText += ` (${skillStatus})`;
      }
      rectWidth = Math.max(120, displayText.length * 7);
      rectHeight = 45;
    } else if (node.type === 'agent') {
      // Show agent type more clearly
      const domain = node.metadata?.domain || '';
      if (domain && domain !== 'general') {
        displayText = `${node.name} (${domain})`;
      }
      rectWidth = Math.max(100, displayText.length * 8);
      rectHeight = 40;
    } else {
      rectWidth = Math.max(80, node.name.length * 8);
      rectHeight = 40;
    }
    
    // Node rectangle
    nodeGroup.append('rect')
      .attr('x', pos.x - rectWidth/2)
      .attr('y', pos.y - rectHeight/2)
      .attr('width', rectWidth)
      .attr('height', rectHeight);
    
    // Node text - handle multiline for skills
    if (node.type === 'skill' && displayText.length > 20) {
      // Split long skill names into multiple lines
      const words = displayText.split(' ');
      const lines = [];
      let currentLine = '';
      
      words.forEach(word => {
        if ((currentLine + word).length > 18) {
          if (currentLine) lines.push(currentLine.trim());
          currentLine = word + ' ';
        } else {
          currentLine += word + ' ';
        }
      });
      if (currentLine) lines.push(currentLine.trim());
      
      lines.forEach((line, i) => {
        nodeGroup.append('text')
          .attr('x', pos.x)
          .attr('y', pos.y - (lines.length - 1) * 6 + i * 12)
          .text(line);
      });
    } else {
      nodeGroup.append('text')
        .attr('x', pos.x)
        .attr('y', pos.y)
        .text(displayText);
    }
    
    // Enhanced tooltip with more details
    let tooltipText = node.description || node.name;
    if (node.type === 'skill') {
      const skillId = node.metadata?.skill_id || '';
      const skillStatus = node.metadata?.status || '';
      tooltipText = `Skill: ${node.name}`;
      if (skillId) tooltipText += `\nID: ${skillId}`;
      if (skillStatus) tooltipText += `\nStatus: ${skillStatus}`;
      if (node.description) tooltipText += `\nDescription: ${node.description}`;
    } else if (node.type === 'agent') {
      const agentId = node.metadata?.agent_id || '';
      const domain = node.metadata?.domain || '';
      tooltipText = `Agent: ${node.name}`;
      if (agentId) tooltipText += `\nID: ${agentId}`;
      if (domain) tooltipText += `\nDomain: ${domain}`;
      if (node.description) tooltipText += `\nDescription: ${node.description}`;
    }
    
    nodeGroup.append('title')
      .text(tooltipText);
  });
  
  // Add legend
  const legend = svg.append('g')
    .attr('class', 'flow-legend')
    .attr('transform', `translate(${width - 150}, 20)`);
  
  const legendItems = [
    { type: 'agent', color: '#4CAF50', label: 'Agent' },
    { type: 'skill', color: '#2196F3', label: 'Skill' },
    { type: 'reasoning', color: '#FF9800', label: 'Reasoning' },
    { type: 'delegation', color: '#9C27B0', label: 'Delegation' }
  ];
  
  legendItems.forEach((item, i) => {
    const legendItem = legend.append('g')
      .attr('transform', `translate(0, ${i * 20})`);
    
    legendItem.append('rect')
      .attr('width', 12)
      .attr('height', 12)
      .attr('fill', item.color)
      .attr('stroke', '#333')
      .attr('stroke-width', 1);
    
    legendItem.append('text')
      .attr('x', 16)
      .attr('y', 6)
      .attr('dy', '0.35em')
      .attr('font-size', '10px')
      .attr('fill', '#333')
      .text(item.label);
  });
}

function calculateNodePositions(nodes, edges, width, height) {
  const positions = {};
  const padding = 60;
  const usableWidth = width - 2 * padding;
  const usableHeight = height - 2 * padding;
  
  // Simple layout: arrange nodes in levels based on their connections
  const levels = [];
  const visited = new Set();
  
  // Find root nodes (nodes with no incoming edges)
  const hasIncoming = new Set();
  edges.forEach(edge => hasIncoming.add(edge.to_node));
  
  const rootNodes = nodes.filter(node => !hasIncoming.has(node.id));
  
  if (rootNodes.length > 0) {
    // BFS to assign levels
    let currentLevel = [rootNodes[0].id];
    levels.push([...currentLevel]);
    visited.add(rootNodes[0].id);
    
    while (currentLevel.length > 0) {
      const nextLevel = [];
      
      currentLevel.forEach(nodeId => {
        edges.forEach(edge => {
          if (edge.from_node === nodeId && !visited.has(edge.to_node)) {
            nextLevel.push(edge.to_node);
            visited.add(edge.to_node);
          }
        });
      });
      
      if (nextLevel.length > 0) {
        levels.push(nextLevel);
      }
      currentLevel = nextLevel;
    }
  }
  
  // Add any remaining nodes to the last level
  const remainingNodes = nodes.filter(node => !visited.has(node.id));
  if (remainingNodes.length > 0) {
    if (levels.length === 0) {
      levels.push(remainingNodes.map(n => n.id));
    } else {
      levels[levels.length - 1].push(...remainingNodes.map(n => n.id));
    }
  }
  
  // Calculate positions
  levels.forEach((level, levelIndex) => {
    const y = padding + (levelIndex / Math.max(1, levels.length - 1)) * usableHeight;
    
    level.forEach((nodeId, nodeIndex) => {
      const x = padding + (nodeIndex / Math.max(1, level.length - 1)) * usableWidth;
      positions[nodeId] = { x: level.length === 1 ? width / 2 : x, y };
    });
  });
  
  return positions;
}

// Modal event handlers
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('flowModal');
  const closeBtn = document.getElementById('closeModal');
  
  // Close modal when clicking the close button
  closeBtn.addEventListener('click', () => {
    modal.classList.add('hidden');
  });
  
  // Close modal when clicking outside the modal content
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.add('hidden');
    }
  });
  
  // Close modal with Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      modal.classList.add('hidden');
    }
  });
});
