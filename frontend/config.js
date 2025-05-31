// Frontend configuration
const CONFIG = {
    // Default to local development URLs
    API_URL: 'http://localhost:8000',
    LIFECYCLE_URL: 'http://localhost:8001',
    AGENT_URL: 'http://localhost:8003',
    SKILL_URL: 'http://localhost:8002',
    
    // Check if we're running in Azure environment
    init: function() {
      // This hostname check detects if we're running on Azure Container Apps
      if (window.location.hostname.includes('azurecontainerapps.io')) {
        this.API_URL = 'https://agent-platform-api.purplewater-c0416f2a.eastus.azurecontainerapps.io';
        this.LIFECYCLE_URL = 'https://agent-platform-lifecycle.purplewater-c0416f2a.eastus.azurecontainerapps.io';
        this.AGENT_URL = 'https://agent-platform-agent.purplewater-c0416f2a.eastus.azurecontainerapps.io';
        this.SKILL_URL = 'https://agent-platform-skill.purplewater-c0416f2a.eastus.azurecontainerapps.io';
      }
      console.log('Environment configured:', 
        window.location.hostname.includes('azurecontainerapps.io') ? 'Azure' : 'Local');
    }
  };
  
  // Initialize configuration
  CONFIG.init();