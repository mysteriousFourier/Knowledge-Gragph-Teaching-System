// 鑰佸笀绔疛avaScript鍔熻兘

console.log('教师端 JavaScript 加载完成');


let isLoggedIn = false;
let isLecturing = false;
let isRecording = false;
let isPlayingAudio = false;
let currentChapter = null;
let qaHistory = [];
let supplementDrafts = [];


let lectureRecords = [];
let currentLecturePosition = 0;  
let currentLectureProgress = 0;
let audioStartTime = null;

let graphData = { nodes: [], edges: [] };
let currentNodeEditorState = null;
let currentEdgeEditorState = null;


let graphZoomLevel = 1;
let graphPanX = 0;
let graphPanY = 0;
let isGraphFullScreen = false;
let isDragging = false;
let isPanning = false;
let dragStartX = 0;
let dragStartY = 0;
let panStartX = 0;
let panStartY = 0;
let draggedNode = null;
let draggedNodeId = null;
let draggedNodeStartX = 0;
let draggedNodeStartY = 0;

let graphSpacingFactor = 1.0;


let wheelZoomTimeout = null;

let teacherPlaybackState = {
    isPlaying: false,
    isPaused: false,
    currentPosition: 0,      // 褰撳墠鎾斁鍒扮殑瀛楃浣嶇疆
    currentUtterance: null,  // 褰撳墠璇煶瀵硅薄
    fullContent: '',
    showFullContent: false,
    highlightedNodes: new Set() // 褰撳墠楂樹寒鐨勮妭鐐笽D闆嗗悎
};

let teacherKnowledgePoints = [];
let savedChapterListRequestToken = 0;
let lectureChapterListRequestToken = 0;
let chapterListContentRequestToken = 0;
let chapterCachePromise = null;

// ==================== API閰嶇疆 ====================

function normalizeBaseUrl(value, fallback) {
    return (value || fallback).replace(/\/+$/, '');
}

const APP_CONFIG = window.__APP_CONFIG__ || {};
const EDUCATION_API_ROOT = normalizeBaseUrl(APP_CONFIG.educationApiBaseUrl, 'http://localhost:8001');
const MAINTENANCE_API_ROOT = normalizeBaseUrl(APP_CONFIG.maintenanceApiBaseUrl, 'http://localhost:8002');
const BACKEND_ADMIN_ROOT = normalizeBaseUrl(APP_CONFIG.backendAdminBaseUrl, 'http://localhost:8080');
const API_BASE_URL = `${EDUCATION_API_ROOT}/api/education`;
const MAINTENANCE_API_URL = `${MAINTENANCE_API_ROOT}/api/maintenance`;
const EMBEDDED_GRAPH_ENABLED = false;

function openBackendGraphAdmin() {
    window.open(`${BACKEND_ADMIN_ROOT}/admin`, '_blank', 'noopener');
}

// ==================== API璋冪敤鍑芥暟 ====================

async function callAPI(endpoint, method = 'GET', data = null) {
    /**
     * 閫氱敤API璋冪敤鍑芥暟锛堟暀鑲叉ā寮廇PI锛?     * @param {string} endpoint - API绔偣
     * @param {string} method - HTTP鏂规硶
     * @param {object} data - 璇锋眰鏁版嵁
     * @returns {Promise<object>} - API鍝嶅簲
     */
    try {
        const apiKey = getUserApiKey();
        if (apiKey && data && method !== 'GET') {
            data.api_key = apiKey;
        }

        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }

        if (method === 'GET') {
            options.cache = 'no-store';
        }

        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

        if (!response.ok) {
            let errMsg = `API閿欒: ${response.status}`;
            try {
                const errorData = await response.json();
                errMsg = errorData.detail || errMsg;
            } catch (_) {}
            throw new Error(errMsg);
        }

        return await response.json();
    } catch (error) {
        console.error('API璋冪敤澶辫触:', error.message || error);

                if (error instanceof TypeError) {
            showAPIConnectionError();
        }

        throw error;
    }
}

// 鏄剧ずAPI杩炴帴閿欒鎻愮ず
function showAPIConnectionError() {
    
    const existingError = document.getElementById('api-connection-error');
    if (existingError) {
        existingError.remove();
    }

    
    const errorDiv = document.createElement('div');
    errorDiv.id = 'api-connection-error';
    errorDiv.className = 'api-connection-error';
    errorDiv.innerHTML = `
        <div class="api-error-content">
            <span class="api-error-icon">⚠</span>
            <div class="api-error-text">
                <div class="api-error-title">API 连接失败</div>
                <div class="api-error-message">服务可能已中断，请点击下方按钮重新连接。</div>
            </div>
            <button onclick="reconnectAPI()" class="btn btn-primary btn-small">重新连接</button>
            <button onclick="closeAPIError()" class="btn btn-secondary btn-small">关闭</button>
        </div>
    `;

    document.body.appendChild(errorDiv);

    // 5绉掑悗鑷姩鍏抽棴
    setTimeout(() => {
        if (document.getElementById('api-connection-error')) {
            closeAPIError();
        }
    }, 5000);
}

// 閲嶆柊杩炴帴API
async function reconnectAPI() {
    showToast('正在重新连接 API...', 'info');

    // 鍏抽棴閿欒鎻愮ず
    closeAPIError();

    // 绛夊緟2绉?    await new Promise(resolve => setTimeout(resolve, 2000));

    
    try {
        const response = await fetch(`${EDUCATION_API_ROOT}/api/health`);
        if (response.ok) {
            showToast('API 已连接', 'success');
            // 閲嶆柊鍔犺浇褰撳墠鏁版嵁
            refreshGraph();
            if (currentChapter) {
                loadTeacherLectureContent(document.getElementById('lecture-note').value || '');
            }
        } else {
            throw new Error('API not responding');
        }
    } catch (error) {
        console.error('閲嶆柊杩炴帴澶辫触:', error);
        showAPIConnectionError();
    }
}

// 鍏抽棴API閿欒鎻愮ず
function closeAPIError() {
    const errorDiv = document.getElementById('api-connection-error');
    if (errorDiv) {
        errorDiv.remove();
    }
}

async function callMaintenanceAPI(endpoint, method = 'GET', data = null) {
    /**
     * 璋冪敤鍚庡彴缁存姢API
     * @param {string} endpoint - API绔偣
     * @param {string} method - HTTP鏂规硶
     * @param {object} data - 璇锋眰鏁版嵁
     * @returns {Promise<object>} - API鍝嶅簲
     */
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }

        if (method === 'GET') {
            options.cache = 'no-store';
        }

        const response = await fetch(`${MAINTENANCE_API_URL}${endpoint}`, options);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `API 错误: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('后台维护 API 调用失败:', error);
        throw error;
    }
}

async function generateLectureWithAPI(chapter) {
    /**
     * 璋冪敤鍚庣API鐢熸垚鎺堣鏂囨
     * @param {object} chapter - 绔犺妭鏁版嵁
     */
    try {
        showToast('正在生成授课文案...', 'info');

        const response = await callAPI('/generate-lecture', 'POST', {
            chapter_id: chapter.id,
            chapter_title: chapter.title,
            chapter_content: chapter.content,
            style: 'guided',
            model: 'deepseek-v4pro'
        });

        if (response.success) {
            const lectureContent = response.content;

            // 鏄剧ず鎺堣鏂囨
            document.getElementById('lecture-note').value = lectureContent;
                        const floatNote = document.getElementById('lecture-note-float');
            if (floatNote) {
                floatNote.value = lectureContent;
            }

            // 鍔犺浇鍒版暀甯堢鎺堣灞曠ず鍖哄煙
            loadTeacherLectureContent(lectureContent);

            showToast(`授课文案已生成（${response.model || 'deepseek-v4pro'}）`, 'success');

            // 鎾斁AI璇煶
            playAudioText(lectureContent);
        } else {
            throw new Error(response.error || '生成失败');
        }
    } catch (error) {
        console.error('生成授课文案失败:', error);
        showToast('生成失败，已使用本地兜底文案', 'warning');
        generateLocalLecture(chapter);
    }
}

async function askQuestionWithAPI(question) {
    /**
     * 璋冪敤鍚庣API鍥炵瓟闂
     * @param {string} question - 闂
     * @returns {Promise<string>} - 绛旀
     */
    try {
        const response = await callAPI('/ask-question', 'POST', {
            question: question
        });

        if (response.success) {
            return response.answer;
        } else {
            throw new Error(response.error || '回答失败');
        }
    } catch (error) {
        console.error('回答问题失败:', error);
        throw error;
    }
}

async function naturalSupplementWithAPI(originalText, supplement) {
    /**
     * 璋冪敤鍚庣API杩涜鑷劧琛ュ厖
     * @param {string} originalText - 鍘熸枃
     * @param {string} supplement - 琛ュ厖鍐呭
     * @returns {Promise<string>} - 铻嶅悎鍚庣殑鏂囨湰
     */
    try {
        const response = await callAPI('/natural-supplement', 'POST', {
            original_text: originalText,
            supplement: supplement
        });

        if (response.success) {
            return response.result;
        } else {
            throw new Error(response.error || '补充失败');
        }
    } catch (error) {
        console.error('自然补充失败:', error);
        throw error;
    }
}

// ==================== 鏈湴澶囩敤鍑芥暟 ====================

function generateLocalLecture(chapter) {
    /**
     * 鏈湴鐢熸垚鎺堣鏂囨锛堝鐢ㄦ柟妗堬級
     * @param {object} chapter - 绔犺妭鏁版嵁
     */
    let generatedLecture = '';

    try {
        
        let graphData = null;

        
        if (chapter.content.trim().startsWith('{')) {
            try {
                const parsed = JSON.parse(chapter.content);

                
                if (parsed.graph && parsed.graph.nodes) {
                    // 鏍煎紡1: { graph: { nodes: [...], edges: [...] } }
                    graphData = parsed.graph;
                } else if (parsed.nodes) {
                    // 鏍煎紡2: { nodes: [...], edges: [...] }
                    graphData = parsed;
                }
            } catch (e) {
                console.log('Content is not valid JSON, using plain text fallback');
            }
        }

        if (graphData && graphData.nodes && graphData.nodes.length > 0) {
            generatedLecture = generateLectureFromGraph(chapter.title, graphData);
        } else {
            generatedLecture = `今天我们学习 ${chapter.title}。\n\n${chapter.content}\n\n接下来我们通过例子进一步理解这些知识点。`;
        }
    } catch (error) {
        console.error('鐢熸垚鎺堣鏂囨鍑洪敊:', error);
        generatedLecture = `今天我们学习 ${chapter.title}。\n\n${chapter.content}\n\n接下来我们通过例子进一步理解这些知识点。`;
    }

    document.getElementById('lecture-note').value = generatedLecture;
    const floatNote = document.getElementById('lecture-note-float');
    if (floatNote) {
        floatNote.value = generatedLecture;
    }
    showToast('已生成本地授课文案', 'info');
    playAudioText(generatedLecture);
}

/**
 * 浠庣煡璇嗗浘璋辩敓鎴愭巿璇炬枃妗? * @param {string} title - 绔犺妭鏍囬
 * @param {object} graphData - 鐭ヨ瘑鍥捐氨鏁版嵁
 * @returns {string} - 鎺堣鏂囨
 */
function generateLectureFromGraph(title, graphData) {
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || graphData.relations || [];

    const concepts = nodes.filter(n => n.type === 'concept' || !n.type || n.label);
    const entities = nodes.filter(n => n.type === 'entity');

    
    const nodeMap = {};
    nodes.forEach(node => {
        nodeMap[node.id] = node;
    });

    const adj = {};
    concepts.forEach(node => {
        adj[node.id] = [];
    });

    edges.forEach(edge => {
        const sourceId = edge.source;
        const targetId = edge.target;
        if (adj[sourceId] && !adj[sourceId].includes(targetId)) {
            adj[sourceId].push(targetId);
        }
    });

        const allTargetIds = new Set(edges.map(e => e.target));
    const startNodes = concepts.filter(n => !allTargetIds.has(n.id));

    
    const orderedConcepts = [];
    const visited = new Set();

    function bfs(nodeId) {
        if (visited.has(nodeId)) return;
        visited.add(nodeId);
        if (nodeMap[nodeId]) {
            orderedConcepts.push(nodeMap[nodeId]);
        }
        if (adj[nodeId]) {
            adj[nodeId].forEach(childId => bfs(childId));
        }
    }

    startNodes.forEach(node => bfs(node.id));
    // 娣诲姞鍓╀綑鏈闂殑鑺傜偣
    concepts.forEach(node => {
        if (!visited.has(node.id)) {
            orderedConcepts.push(node);
        }
    });

    
    let lecture = `同学们好，今天我们学习 ${title}。\n\n`;

    lecture += `首先，我们先梳理本章的核心知识点。\n\n`;

    // 鎸夐『搴忚瑙ｇ煡璇嗙偣
    orderedConcepts.forEach((concept, index) => {
        const label = concept.label || concept.id;
        const description = concept.description || concept.content || concept.definition || '这是一个重要概念';

        lecture += `${index + 1}. ${label}\n`;
        lecture += `   ${description}\n\n`;

        
        const outgoingEdges = edges.filter(e => e.source === concept.id);
        outgoingEdges.forEach(edge => {
            const targetNode = nodeMap[edge.target];
            if (targetNode) {
                const relation = edge.relation || edge.type || '相关';
                const targetLabel = targetNode.label || targetNode.id;
                lecture += `   ${label} 与 ${targetLabel} 的关系是「${relation}」，这是一个需要关注的知识关联。\n`;
            }
        });
        lecture += '\n';
    });

    
    if (entities.length > 0) {
        lecture += `接下来，我们介绍一些相关工具和实例：\n\n`;
        entities.forEach((entity, index) => {
            const label = entity.label || entity.id;
            const description = entity.description || entity.content || entity.definition || '';
            lecture += `${index + 1}. ${label}\n`;
            if (description) {
                lecture += `   ${description}\n`;
            }
            lecture += '\n';
        });
    }

    // 鎬荤粨閮ㄥ垎
    lecture += `通过以上学习，我们已经掌握了 ${title} 的核心内容。\n\n`;
    lecture += `接下来，我们通过具体例子加深理解。\n\n`;
    lecture += `同学们有问题吗？`;

    return lecture;
}

// ==================== 鐧诲綍鍔熻兘 ====================

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!username || !password) {
        showToast('Please enter username and password', 'warning');
        return;
    }

    let data = null;
    try {
        const response = await fetch(`${EDUCATION_API_ROOT}/api/teacher/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username, password })
        });
        data = await response.json().catch(() => null);
        if (!response.ok) {
            throw new Error((data && data.detail) || `Login API error: ${response.status}`);
        }
    } catch (error) {
        console.error('Teacher login failed:', error);
        if (error instanceof TypeError) {
            showAPIConnectionError();
        }
        showToast('登录服务不可用，请检查后端服务', 'error');
        return;
    }

    if (data && data.success) {
        isLoggedIn = true;
        document.getElementById('current-user').textContent = data.username || username;

        // 鍏堟樉绀簍oast
        showToast('Login successful', 'success');

        // 寤惰繜鍒囨崲椤甸潰锛岀‘淇滵OM鎿嶄綔瀹屾垚
        setTimeout(() => {
            try {
                const loginPage = document.getElementById('login-page');
                const teacherPage = document.getElementById('teacher-page');

                if (loginPage && teacherPage) {
                    loginPage.classList.remove('active');
                    teacherPage.classList.add('active');
                    loadInitialData();
                    console.log('椤甸潰鍒囨崲鎴愬姛');
                } else {
                    console.error('Page elements not found');
                    showToast('页面切换失败', 'error');
                }
            } catch (error) {
                console.error('椤甸潰鍒囨崲閿欒:', error);
                showToast('页面切换失败', 'error');
            }
        }, 500);
    } else {
        showToast((data && data.error) || '用户名或密码错误');
    }
}

function logout() {
    isLoggedIn = false;
    isLecturing = false;

    setTimeout(() => {
        const loginPage = document.getElementById('login-page');
        const teacherPage = document.getElementById('teacher-page');

        if (loginPage && teacherPage) {
            teacherPage.classList.remove('active');
            loginPage.classList.add('active');

            document.getElementById('username').value = '';
            document.getElementById('password').value = '';

            showToast('Logged out', 'info');
        }
    }, 100);
}

// ==================== 椤甸潰鍒囨崲 ====================

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    document.getElementById(pageId).classList.add('active');
}


// ==================== 妯″紡鍒囨崲 ====================

function switchMode(mode) {
    const preparePanel = document.getElementById('prepare-mode-panel');
    const lecturePanel = document.getElementById('lecture-mode-panel');
    const prepareBtn = document.getElementById('btn-prepare-mode');
    const lectureBtn = document.getElementById('btn-lecture-mode');

    if (mode === 'prepare') {
        if (preparePanel) preparePanel.classList.add('active');
        if (lecturePanel) lecturePanel.classList.remove('active');
        if (prepareBtn) prepareBtn.classList.add('active');
        if (lectureBtn) lectureBtn.classList.remove('active');
        showToast('已切换到备课模式');
    } else if (mode === 'lecture') {
        if (preparePanel) preparePanel.classList.remove('active');
        if (lecturePanel) lecturePanel.classList.add('active');
        if (prepareBtn) prepareBtn.classList.remove('active');
        if (lectureBtn) lectureBtn.classList.add('active');
        showToast('已切换到授课模式');
    }
}

// ==================== 闂瓟娴獥鍒囨崲 ====================

function toggleQaWindow() {
    const qaWindow = document.getElementById('qa-float-window');
    if (qaWindow) {
        if (qaWindow.classList.contains('hidden')) {
            qaWindow.classList.remove('hidden');
        } else {
            qaWindow.classList.add('hidden');
        }
    }
}

// ==================== 瀵煎叆鐭ヨ瘑鍥捐氨鍔熻兘 ====================

async function importKnowledgeGraph() {
    const fileInput = document.getElementById('graphml-file-input');
    const titleInput = document.getElementById('chapter-title');

    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('请选择图谱文件', 'warning');
        return;
    }

    const file = fileInput.files[0];
    let chapterTitle = titleInput.value.trim();

    if (!chapterTitle) {
        // 浠庢枃浠跺悕鎻愬彇鍚嶇О
        chapterTitle = file.name.replace(/\.[^/.]+$/, '');
    }

    showToast('正在导入知识图谱，请稍候...', 'info');

    try {
        
        const fileContent = await readFileContent(file);

        
        let graphData;
        if (file.name.endsWith('.graphml') || file.name.endsWith('.xml')) {
            // GraphML鏂囦欢 - 鐩存帴鍙戦€佹枃浠惰矾寰勭粰鍚庣
            showToast('正在解析 GraphML 文件...', 'info');

            // 娉ㄦ剰锛氱敱浜庢祻瑙堝櫒瀹夊叏闄愬埗锛屽墠绔棤娉曠洿鎺ヤ紶閫掓枃浠惰矾寰勭粰鍚庣
            
            return;
        } else {
            
            try {
                graphData = JSON.parse(fileContent);

                
                if (!graphData.nodes && !graphData.graph) {
                    throw new Error('无效的知识图谱 JSON 格式');
                }

                if (graphData.graph) {
                    graphData = graphData.graph;
                }
            } catch (e) {
                showToast('JSON 解析失败，请检查文件格式', 'error');
                return;
            }
        }

        
        const result = await callMaintenanceAPI('/import-graph', 'POST', {
            graph_data: graphData,
            graph_name: chapterTitle
        });

        if (result.success) {
            const nodeSuccess = result.imported_nodes.filter(n => n.status === 'success').length;
            const edgeSuccess = result.imported_edges.filter(e => e.status === 'success').length;

            showToast('知识图谱已导入', 'success');
            showToast(`节点: ${nodeSuccess}/${result.total_nodes}, 关系: ${edgeSuccess}/${result.total_edges}`, 'info');

            // 娓呯┖杈撳叆
            fileInput.value = '';
            titleInput.value = '';

            // 鑷姩鍒锋柊鐭ヨ瘑鍥捐氨
            await updateKnowledgeGraph();

            // 鑷姩鐢熸垚鎺堣鏂囨
            showToast('正在生成授课文案...', 'info');
            await generateLectureWithAPI({
                title: chapterTitle,
                content: '',
                graph_data: graphData
            });
        } else {
            showToast('知识图谱导入失败', 'error');
        }
    } catch (error) {
        console.error('导入知识图谱失败:', error);
        let errorMsg = '导入失败，请稍后重试';
        if (error.response) {
            const errorData = error.response.data || error.response;
            if (typeof errorData === 'string') {
                errorMsg = errorData;
            } else if (errorData.detail) {
                errorMsg = errorData.detail;
            } else if (errorData.message) {
                errorMsg = errorData.message;
            }
        } else if (error.message) {
            errorMsg = error.message;
        }
        showToast(errorMsg, 'error');
    }
}

// 涓婁紶骞跺鍏raphML鏂囦欢
async function uploadAndImportGraphML(file, chapterTitle) {
    try {
        const fileContent = await readFileContent(file);

        
        const rangeSelect = document.getElementById('import-node-range');
        const countInput = document.getElementById('import-node-count');
        const totalNodes = window._graphmlTotalNodes || 0;
        let maxNodes = null;
        const range = rangeSelect ? rangeSelect.value : 'all';

        if (range === 'half' && totalNodes > 0) {
            maxNodes = Math.ceil(totalNodes / 2);
        } else if (range === 'custom') {
            maxNodes = parseInt(countInput ? countInput.value : '0');
            if (!maxNodes || maxNodes < 1) {
                showToast('请输入有效的节点数量', 'warning');
                return;
            }
        }

        showToast('正在加载图谱...', 'info');

        // Step 1: Parse and render locally (fast, no network)
        var graphData = parseGraphMLLocally(fileContent, maxNodes);
        if (graphData.nodes.length > 0) {
            renderVisGraph(graphData);
            showToast('已加载: ' + graphData.stats.node_count + ' 个节点，' + graphData.stats.edge_count + ' 条关系', 'success');
        } else {
            showToast('文件中未找到节点', 'error');
            return;
        }

        // Step 2: Import to backend database (non-blocking)
        callMaintenanceAPI('/import-graphml', 'POST', {
            file_content: fileContent,
            graph_name: chapterTitle
        }).then(function(result) {
            if (result.success) {
                showToast('已保存到后端图谱', 'success');
            }
        }).catch(function(err) {
            console.warn('后端保存已跳过:', err);
        });

        // Set current chapter
        var titleInput = document.getElementById('chapter-title');
        var cTitle = titleInput ? titleInput.value.trim() : file.name.replace(/\.[^/.]+$/, '');
        if (cTitle) currentChapter = { id: 'chapter_' + cTitle, title: cTitle };

        // Clear file input only
        document.getElementById('graphml-file-input').value = '';

    } catch (error) {
        console.error('GraphML 导入失败:', error);
        showToast(error.message || '导入失败', 'error');
    }
}

// Local GraphML parser - robust parsing that handles malformed XML
function parseGraphMLLocally(xmlString, maxNodes) {
    // Use regex to extract nodes and edges (bypasses strict XML parsing)
    var colorMap = {
        proposition: '#e74c3c', derivation: '#3498db', discussion: '#1abc9c',
        chapter: '#f39c12', formula: '#2ecc71', definition: '#9b59b6',
        concept: '#10b981', note: '#f59e0b', observation: '#3b82f6'
    };

    // Build key map from <key> elements
    var keyMap = {};
    var keyRe = /<key\s+id="([^"]+)"\s+[^>]*attr\.name="([^"]+)"/g;
    var m;
    while ((m = keyRe.exec(xmlString)) !== null) {
        keyMap[m[1]] = m[2];
    }

    // Extract all <node> blocks
    var allNodes = [];
    var nodeRe = /<node\s+id="([^"]+)"[\s\S]*?<\/node>/g;
    while ((m = nodeRe.exec(xmlString)) !== null) {
        var nodeId = m[1];
        var nodeBlock = m[0];
        var attrs = {};
        var dataRe = /<data\s+key="([^"]+)">([\s\S]*?)<\/data>/g;
        var dm;
        while ((dm = dataRe.exec(nodeBlock)) !== null) {
            var key = keyMap[dm[1]] || dm[1];
            attrs[key] = dm[2].trim();
        }
        var nType = attrs.type || 'unknown';
        var c = colorMap[nType] || '#95a5a6';
        allNodes.push({
            id: nodeId,
            label: latexToText((attrs.label || nodeId).substring(0, 40)),
            title: latexToText((attrs.label || nodeId).substring(0, 100)),
            color: { background: c, border: c, highlight: { background: c, border: '#2c3e50' }, hover: { background: c, border: '#2c3e50' } },
            size: 20,
            borderWidth: 1,
            font: { size: 12, color: '#2c3e50', face: 'Microsoft YaHei, sans-serif' },
            shape: 'dot',
            _type: nType,
            _content: attrs.content || '',
            _full_label: attrs.label || '',
            _source: attrs.source || ''
        });
    }

    // Apply maxNodes limit
    var nodes = maxNodes ? allNodes.slice(0, maxNodes) : allNodes;
    var nodeIds = {};
    nodes.forEach(function(n) { nodeIds[n.id] = true; });

    // Extract edges (only between retained nodes)
    var edges = [];
    var edgeRe = /<edge\s+[^>]*source="([^"]+)"[^>]*target="([^"]+)"[\s\S]*?<\/edge>/g;
    while ((m = edgeRe.exec(xmlString)) !== null) {
        var src = m[1], tgt = m[2];
        if (!nodeIds[src] || !nodeIds[tgt]) continue;
        var edgeBlock = m[0];
        var eAttrs = {};
        var eDataRe = /<data\s+key="([^"]+)">([\s\S]*?)<\/data>/g;
        while ((dm = eDataRe.exec(edgeBlock)) !== null) {
            var eKey = keyMap[dm[1]] || dm[1];
            eAttrs[eKey] = dm[2].trim();
        }
        var rtype = eAttrs.rtype || eAttrs.type || '';
        var strength = parseFloat(eAttrs.strength || '1');
        edges.push({
            from: src, to: tgt,
            label: rtype,
            title: rtype + (eAttrs.description ? ': ' + eAttrs.description : ''),
            width: Math.max(1, Math.min(5, strength * 4)),
            arrows: 'to',
            color: { color: '#bdc3c7', opacity: 0.6 },
            smooth: { type: 'continuous', roundness: 0.5 }
        });
    }

    return { nodes: nodes, edges: edges, stats: { node_count: nodes.length, edge_count: edges.length } };
}

// Preview node count when file is selected (parsed locally, no API needed)
async function previewGraphNodeCount() {
    const fileInput = document.getElementById('graphml-file-input');
    const infoEl = document.getElementById('import-node-info');
    if (!fileInput || !fileInput.files.length || !infoEl) {
        if (infoEl) infoEl.textContent = '';
        return;
    }
    const file = fileInput.files[0];
    if (!file.name.endsWith('.graphml') && !file.name.endsWith('.xml')) {
        infoEl.textContent = '';
        return;
    }
    try {
        const content = await readFileContent(file);
        // Use regex for robust counting because DOMParser may fail on malformed XML.
        var nodeCount = (content.match(/<node\s+id="/g) || []).length;
        var edgeCount = (content.match(/<edge\s+/g) || []).length;

        window._graphmlTotalNodes = nodeCount;
        window._graphmlFileContent = content;

        infoEl.textContent = 'Detected: ' + nodeCount + ' nodes, ' + edgeCount + ' edges';
        updateImportRangeInfo();
    } catch (e) {
        infoEl.textContent = 'Unable to parse file';
    }
}

// Handle range selector change and update info text
function updateImportRangeInfo() {
    const rangeSelect = document.getElementById('import-node-range');
    const countInput = document.getElementById('import-node-count');
    const infoEl = document.getElementById('import-node-info');
    if (!rangeSelect || !countInput || !infoEl) return;

    const total = window._graphmlTotalNodes || 0;

    
    if (rangeSelect.value === 'custom') {
        countInput.style.display = '';
        countInput.max = total;
        countInput.placeholder = total ? `1-${total}` : 'Enter count';
    } else {
        countInput.style.display = 'none';
    }

    
    if (!total) {
        infoEl.textContent = '';
        return;
    }
    if (rangeSelect.value === 'all') {
        infoEl.textContent = `Will import: ${total} nodes`;
    } else if (rangeSelect.value === 'half') {
        infoEl.textContent = `Will import: ${Math.ceil(total / 2)} / ${total} nodes`;
    } else {
        infoEl.textContent = `Detected: ${total} nodes - enter count above`;
    }
}

// 璇诲彇鏂囦欢鍐呭
function readFileContent(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = function(e) {
            resolve(e.target.result);
        };

        reader.onerror = function(e) {
            reject(new Error('璇诲彇鏂囦欢澶辫触'));
        };

        
        if (file.name.endsWith('.json')) {
            reader.readAsText(file);
        } else if (file.name.endsWith('.md') || file.name.endsWith('.txt')) {
            reader.readAsText(file);
        } else {
            // 榛樿浠ユ枃鏈鍙?            reader.readAsText(file);
        }
    });
}



let visNetworkInstance = null;
let visGraphVisible = false;

function renderVisGraph(data) {
    const container = document.getElementById('vis-graph-container');
    if (!container) return;

    container.style.display = 'block';
    container.style.height = '600px';
    visGraphVisible = true;

    
    if (visNetworkInstance) {
        visNetworkInstance.destroy();
        visNetworkInstance = null;
    }

    // Build vis.js DataSets
    // Node type color map (same as parser)
    var nodeColorMap = {
        proposition: '#e74c3c', derivation: '#3498db', discussion: '#1abc9c',
        chapter: '#f39c12', formula: '#2ecc71', definition: '#9b59b6',
        concept: '#10b981', note: '#f59e0b', observation: '#3b82f6'
    };

    const nodes = new vis.DataSet(data.nodes.map(function(n) {
        // Labels on graph: readable plain text
        var displayLabel = n.label || n.id;
        var tooltipLabel = n.title || n.label || n.id;
        if (displayLabel.indexOf('$') !== -1) displayLabel = latexToText(displayLabel);
        if (tooltipLabel.indexOf('$') !== -1) tooltipLabel = latexToText(tooltipLabel);
        // Determine node color: prefer explicit color object, then color map by type, then default
        var nodeColor;
        if (typeof n.color === 'object' && n.color.background) {
            nodeColor = n.color;
        } else {
            var c = (typeof n.color === 'string') ? n.color : (nodeColorMap[(n.type || '').toLowerCase()] || '#95a5a6');
            nodeColor = {
                background: c, border: c,
                highlight: { background: c, border: '#2c3e50' },
                hover: { background: c, border: '#2c3e50' }
            };
        }
        return {
            id: n.id,
            label: formatGraphLabel(displayLabel),
            title: tooltipLabel,
            color: nodeColor,
            size: parseFloat(n.size) || 16,
            borderWidth: parseInt(n.borderWidth) || 1,
            font: { size: 13, color: '#1f2937', face: 'Microsoft YaHei, sans-serif', multi: true },
            shape: 'box',
            margin: { top: 8, right: 10, bottom: 8, left: 10 },
            widthConstraint: { minimum: 90, maximum: 190 },
            heightConstraint: { minimum: 38 },
            _type: n.type || '',
            _content: n.content || '',
            _source: n.source || '',
            _full_label: n.full_label || n.label || ''
        };
    }));

    const edges = new vis.DataSet(data.edges.map(e => ({
        from: e.from,
        to: e.to,
        label: e.label || '',
        title: e.title || '',
        width: parseFloat(e.width) || 1,
        arrows: 'to',
        color: (typeof e.color === 'object' && e.color.color) ? e.color : { color: '#95a5a6', opacity: 0.6 },
        smooth: { type: 'continuous', roundness: 0.5 }
    })));

    const options = {
        layout: {
            improvedLayout: true
        },
        physics: {
            enabled: true,
            repulsion: {
                centralGravity: 0.08,
                springLength: 210,
                springConstant: 0.045,
                nodeDistance: 190,
                damping: 0.62
            },
            maxVelocity: 35,
            minVelocity: 0.1,
            solver: 'repulsion',
            stabilization: { enabled: true, iterations: 260, updateInterval: 25 }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: false,
            keyboard: { enabled: true },
            zoomView: true,
            dragView: true,
            dragNodes: true
        },
        nodes: { borderWidthSelected: 3 },
        edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.65 } },
            font: { size: 0, align: 'middle' },
            selectionWidth: 2
        }
    };

    visNetworkInstance = new vis.Network(container, { nodes, edges }, options);

    // Stop physics after stabilization so nodes don't drift
    visNetworkInstance.once('stabilizationIterationsDone', function() {
        visNetworkInstance.setOptions({ physics: { enabled: false } });
        visNetworkInstance.fit({ animation: { duration: 350, easingFunction: 'easeInOutQuad' } });
    });

    // Node click: show detail panel
    visNetworkInstance.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const nodeData = nodes.get(nodeId);
            showVisNodeDetail(nodeData);
        }
    });

    
    const searchInput = document.getElementById('vis-graph-search');
    if (searchInput) {
        searchInput.oninput = function() {
            const term = this.value.toLowerCase().trim();
            const allNodes = nodes.get();
            if (!term) {
                allNodes.forEach(n => nodes.update({ id: n.id, hidden: false, opacity: 1.0 }));
                return;
            }
            allNodes.forEach(n => {
                const match = (n.label || '').toLowerCase().includes(term)
                    || (n._full_label || '').toLowerCase().includes(term)
                    || (n._content || '').toLowerCase().includes(term)
                    || (n._type || '').toLowerCase().includes(term);
                nodes.update({ id: n.id, hidden: !match, opacity: match ? 1.0 : 0.15 });
            });
        };
    }
}

function showVisNodeDetail(nodeData) {
    const detailEl = document.getElementById('node-detail');
    const contentEl = document.getElementById('node-detail-content');
    if (!detailEl || !contentEl) return;

    let html = `<p><strong>Type:</strong> ${nodeData._type || 'unknown'}</p>`;
    if (nodeData._full_label) {
        html += `<p><strong>Label:</strong> ${renderLatexContent(nodeData._full_label)}</p>`;
    }
    if (nodeData._content) {
        const rendered = renderLatexContent(nodeData._content);
        const short = nodeData._content.length > 800
            ? rendered.substring(0, rendered.lastIndexOf(' ') + 300) + '...'
            : rendered;
        html += `<div style="margin-top:8px;padding:8px;background:#f0f0f0;border-radius:4px;font-size:12px;line-height:1.6;max-height:400px;overflow-y:auto;">${short}</div>`;
    }
    if (nodeData._source) {
        html += `<p style="margin-top:6px;color:#999;font-size:11px;">Source: ${escapeHtml(nodeData._source.split(/[\\/]/).pop())}</p>`;
    }

    contentEl.innerHTML = html;
    detailEl.classList.remove('hidden');
}

function normalizeGraphDataForVis(data) {
    const rawNodes = (data && data.nodes) ? data.nodes : [];
    const rawEdges = (data && (data.edges || data.relations)) ? (data.edges || data.relations) : [];

    return {
        nodes: rawNodes.map(function(n) {
            const metadata = n.metadata || {};
            return {
                id: n.id,
                label: n.label || metadata.label || n.id,
                title: n.title || metadata.label || n.label || n.id,
                type: n.type || metadata.type || n._type || 'concept',
                chapter: n.chapter || metadata.chapter || n._chapter || '',
                content: n.content || n.description || n._content || metadata.description || '',
                source: n.source || metadata.source || n._source || '',
                full_label: n.full_label || n._full_label || n.label || metadata.label || '',
                color: n.color,
                size: n.size,
                borderWidth: n.borderWidth
            };
        }),
        edges: rawEdges
            .map(function(e) {
                const metadata = e.metadata || {};
                const from = e.from || e.source || e.source_id;
                const to = e.to || e.target || e.target_id;
                const relationType = e.type || e.relation_type || e.label || 'related';
                return {
                    id: e.id || metadata.id || `${from}::${relationType}::${to}`,
                    from: from,
                    to: to,
                    label: e.label || relationType,
                    title: e.title || metadata.description || relationType,
                    relationType: relationType,
                    description: metadata.description || e.description || '',
                    chapter: e.chapter || metadata.chapter || '',
                    similarity: e.similarity || e.strength || '',
                    color: e.color,
                    width: e.width
                };
            })
            .filter(function(e) { return e.from && e.to; })
    };
}

function populateGraphChapterFilters(nodes) {
    const chapters = Array.from(new Set(
        (nodes || []).map(function(node) { return node._chapter || ''; }).filter(Boolean)
    )).sort();

    ['vis-graph-chapter-filter', 'review-search-chapter'].forEach(function(selectId) {
        const select = document.getElementById(selectId);
        if (!select) return;
        const currentValue = select.value;
        select.innerHTML = '<option value="">全部章节</option>' + chapters.map(function(chapter) {
            return `<option value="${escapeHtml(chapter)}">${escapeHtml(chapter)}</option>`;
        }).join('');
        if (chapters.indexOf(currentValue) !== -1) {
            select.value = currentValue;
        }
    });
}

function formatGraphLabel(label, maxLength) {
    const text = String(label || '').replace(/\s+/g, ' ').trim();
    const max = maxLength || 42;
    const clipped = text.length > max ? text.slice(0, max - 1) + '…' : text;
    const words = clipped.split(' ');
    if (words.length > 1) {
        const lines = [];
        let current = '';
        words.forEach(function(word) {
            if ((current + ' ' + word).trim().length > 18) {
                if (current) lines.push(current);
                current = word;
            } else {
                current = (current + ' ' + word).trim();
            }
        });
        if (current) lines.push(current);
        return lines.slice(0, 3).join('\n');
    }
    return clipped.match(/.{1,14}/g)?.slice(0, 3).join('\n') || clipped;
}

function formatEdgeLabel(label) {
    const text = String(label || 'related').replace(/\s+/g, ' ').trim();
    return text.length > 24 ? text.slice(0, 21) + '...' : text;
}

function applyVisFilters(nodes, edges) {
    const searchInput = document.getElementById('vis-graph-search');
    const chapterFilter = document.getElementById('vis-graph-chapter-filter');
    const term = ((searchInput && searchInput.value) || '').toLowerCase().trim();
    const chapter = (chapterFilter && chapterFilter.value) || '';
    const visibleNodeIds = new Set();

    nodes.get().forEach(function(node) {
        const chapterMatch = !chapter || node._chapter === chapter;
        const textMatch = !term
            || (node.label || '').toLowerCase().includes(term)
            || (node._full_label || '').toLowerCase().includes(term)
            || (node._content || '').toLowerCase().includes(term)
            || (node._type || '').toLowerCase().includes(term)
            || (node._chapter || '').toLowerCase().includes(term);
        const visible = chapterMatch && textMatch;
        if (visible) visibleNodeIds.add(node.id);
        nodes.update({ id: node.id, hidden: !visible, opacity: visible ? 1.0 : 0.15 });
    });

    edges.get().forEach(function(edge) {
        const visible = visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to);
        edges.update({ id: edge.id, hidden: !visible });
    });
}

function renderKnowledgeGraph() {
    if (!EMBEDDED_GRAPH_ENABLED) {
        updateGraphPanelSummary();
        return;
    }
    renderVisGraph(graphData);
}

function renderVisGraph(data) {
    const container = document.getElementById('vis-graph-container');
    if (!container) return;
    container.style.display = 'block';

    if (visNetworkInstance) {
        visNetworkInstance.destroy();
        visNetworkInstance = null;
    }

    const normalized = normalizeGraphDataForVis(data);
    const nodeColorMap = {
        proposition: '#e74c3c', derivation: '#3498db', discussion: '#1abc9c',
        chapter: '#f39c12', formula: '#2ecc71', definition: '#9b59b6',
        concept: '#10b981', note: '#f59e0b', observation: '#3b82f6'
    };

    const nodes = new vis.DataSet(normalized.nodes.map(function(n) {
        var displayLabel = n.label || n.id;
        var tooltipLabel = n.title || n.label || n.id;
        if (displayLabel.indexOf('$') !== -1) displayLabel = latexToText(displayLabel);
        if (tooltipLabel.indexOf('$') !== -1) tooltipLabel = latexToText(tooltipLabel);
        var nodeColor;
        if (typeof n.color === 'object' && n.color.background) {
            nodeColor = n.color;
        } else {
            var c = (typeof n.color === 'string') ? n.color : (nodeColorMap[(n.type || '').toLowerCase()] || '#95a5a6');
            nodeColor = {
                background: c, border: c,
                highlight: { background: c, border: '#2c3e50' },
                hover: { background: c, border: '#2c3e50' }
            };
        }
        return {
            id: n.id,
            label: formatGraphLabel(displayLabel),
            title: tooltipLabel,
            color: nodeColor,
            size: parseFloat(n.size) || 16,
            borderWidth: parseInt(n.borderWidth) || 1,
            font: { size: 13, color: '#1f2937', face: 'Microsoft YaHei, sans-serif', multi: true },
            shape: 'box',
            margin: { top: 8, right: 10, bottom: 8, left: 10 },
            widthConstraint: { minimum: 90, maximum: 190 },
            heightConstraint: { minimum: 38 },
            _type: n.type || '',
            _content: n.content || '',
            _source: n.source || '',
            _chapter: n.chapter || '',
            _full_label: n.full_label || n.label || ''
        };
    }));

    const edges = new vis.DataSet(normalized.edges.map(function(e) {
        return {
            id: e.id,
            from: e.from,
            to: e.to,
            label: formatEdgeLabel(e.label || e.relationType || 'related'),
            title: e.title || e.label || '',
            width: parseFloat(e.width) || 1.4,
            arrows: 'to',
            color: (typeof e.color === 'object' && e.color.color) ? e.color : { color: '#9ca3af', opacity: 0.45 },
            smooth: { type: 'dynamic', roundness: 0.35 },
            _relation_id: e.id,
            _type: e.relationType || e.label || 'related',
            _description: e.description || '',
            _chapter: e.chapter || '',
            _similarity: e.similarity || ''
        };
    }));

    const options = {
        physics: {
            enabled: true,
            forceAtlas2Based: {
                gravitationalConstant: -50,
                centralGravity: 0.01,
                springLength: 150,
                springConstant: 0.08,
                damping: 0.4
            },
            maxVelocity: 50,
            minVelocity: 0.1,
            solver: 'forceAtlas2Based',
            stabilization: { enabled: true, iterations: 150, updateInterval: 25 }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: false,
            keyboard: { enabled: true },
            zoomView: true,
            dragView: true,
            dragNodes: true
        },
        nodes: { borderWidthSelected: 4 },
        edges: {
            arrows: { to: { enabled: true, scaleFactor: 0.8 } },
            font: {
                size: 11,
                align: 'middle',
                strokeWidth: 3,
                strokeColor: '#ffffff',
                background: '#ffffff'
            }
        }
    };

    visNetworkInstance = new vis.Network(container, { nodes, edges }, options);
    populateGraphChapterFilters(nodes.get());

    visNetworkInstance.once('stabilizationIterationsDone', function() {
        visNetworkInstance.setOptions({ physics: { enabled: false } });
    });

    visNetworkInstance.on('click', function(params) {
        if (params.edges.length > 0) {
            const edgeId = params.edges[0];
            loadEdgeEditor(edgeId, edges.get(edgeId));
            return;
        }
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            loadNodeEditor(nodeId, nodes.get(nodeId));
        }
    });

    const searchInput = document.getElementById('vis-graph-search');
    if (searchInput) {
        searchInput.oninput = function() {
            applyVisFilters(nodes, edges);
        };
    }

    const chapterFilter = document.getElementById('vis-graph-chapter-filter');
    if (chapterFilter) {
        chapterFilter.onchange = function() {
            applyVisFilters(nodes, edges);
        };
    }

    applyVisFilters(nodes, edges);
}

function showVisNodeDetail(nodeData) {
    if (nodeData && nodeData.id) {
        loadNodeEditor(nodeData.id, nodeData);
    }
}

async function loadNodeEditor(nodeId, fallbackData) {
    const detailEl = document.getElementById('node-detail');
    const contentEl = document.getElementById('node-detail-content');
    if (!detailEl || !contentEl) return;

    let nodeData = null;
    try {
        const response = await callMaintenanceAPI(`/get-node?node_id=${encodeURIComponent(nodeId)}`, 'GET');
        nodeData = response.node || response.data || null;
    } catch (error) {
        console.warn('加载节点详情失败，使用前端缓存数据', error);
    }

    const metadata = (nodeData && nodeData.metadata) || {};
    const label = metadata.label || (fallbackData && fallbackData._full_label) || (fallbackData && fallbackData.label) || nodeId;
    const content = (nodeData && nodeData.content) || (fallbackData && fallbackData._content) || '';
    const type = (nodeData && nodeData.type) || (fallbackData && fallbackData._type) || 'concept';
    const chapter = metadata.chapter || (fallbackData && fallbackData._chapter) || '';
    const source = metadata.source || (fallbackData && fallbackData._source) || '';

    currentNodeEditorState = {
        nodeId: nodeId,
        metadata: metadata
    };
    currentEdgeEditorState = null;

    let html = '';
    html += `<div style="display:grid;gap:10px;">`;
    html += `<div><strong>ID:</strong> <span style="font-size:12px;color:#666;">${escapeHtml(nodeId)}</span></div>`;
    html += `<div><strong>类型:</strong> ${escapeHtml(type)}</div>`;
    if (chapter) html += `<div><strong>章节:</strong> ${escapeHtml(chapter)}</div>`;
    if (source) html += `<div><strong>来源:</strong> ${escapeHtml(String(source).split(/[\\\\/]/).pop())}</div>`;
    html += `<label style="font-weight:600;">节点名称</label>`;
    html += `<input id="node-edit-label" type="text" value="${escapeHtml(label)}" style="padding:8px 10px;border:1px solid #ddd;border-radius:6px;">`;
    html += `<label style="font-weight:600;">节点内容</label>`;
    html += `<textarea id="node-edit-content" style="min-height:180px;padding:10px;border:1px solid #ddd;border-radius:6px;line-height:1.5;">${escapeHtml(content)}</textarea>`;
    html += `<div style="display:grid;gap:8px;margin-top:4px;">`;
    html += `<div style="font-weight:600;">关联关系</div>`;
    html += `<div id="node-relation-list" style="display:grid;gap:6px;font-size:12px;color:#374151;">正在加载...</div>`;
    html += `</div>`;
    html += `<div style="display:flex;gap:8px;justify-content:flex-end;">`;
    html += `<button onclick="saveCurrentNodeEdit()" class="btn btn-primary">保存节点</button>`;
    html += `</div>`;
    html += `</div>`;

    contentEl.innerHTML = html;
    detailEl.classList.remove('hidden');
    renderNodeRelationList(nodeId);
}

async function renderNodeRelationList(nodeId) {
    const relationEl = document.getElementById('node-relation-list');
    if (!relationEl) return;

    try {
        const response = await callMaintenanceAPI(`/relations?node_id=${encodeURIComponent(nodeId)}`, 'GET');
        const relations = (response && response.relations) || [];
        if (!relations.length) {
            relationEl.innerHTML = '<div style="color:#9ca3af;">暂无关联关系</div>';
            return;
        }

        const nodeDataSet = visNetworkInstance ? visNetworkInstance.body.data.nodes : null;
        const rows = relations.slice(0, 40).map(function(relation) {
            const sourceId = relation.source_id || relation.source_node || relation.source || '';
            const targetId = relation.target_id || relation.target_node || relation.target || '';
            const direction = sourceId === nodeId ? 'out' : 'in';
            const otherId = sourceId === nodeId ? targetId : sourceId;
            const otherNode = nodeDataSet ? nodeDataSet.get(otherId) : null;
            const otherLabel = (otherNode && (otherNode._full_label || otherNode.label)) || otherId;
            const relationType = relation.relation_type || relation.type || 'related';
            const relationId = relation.id || (relation.metadata && relation.metadata.id) || `${sourceId}::${relationType}::${targetId}`;
            const relationIdClick = escapeHtml(escapeJsString(relationId));
            return `<div style="display:flex;align-items:center;gap:8px;justify-content:space-between;border:1px solid #e5e7eb;border-radius:6px;padding:7px 8px;background:#fafafa;">
                <div style="min-width:0;">
                    <div style="font-weight:600;color:#111827;">${escapeHtml(direction)} / ${escapeHtml(relationType)}</div>
                    <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#6b7280;" title="${escapeHtml(otherLabel)}">${escapeHtml(otherLabel)}</div>
                </div>
                <button class="btn btn-small" onclick="openRelationEditorById('${relationIdClick}')">编辑</button>
            </div>`;
        }).join('');

        relationEl.innerHTML = rows;
    } catch (error) {
        console.warn('加载节点关系失败', error);
        relationEl.innerHTML = '<div style="color:#ef4444;">加载关系失败</div>';
    }
}

async function loadEdgeEditor(edgeId, edgeData) {
    const detailEl = document.getElementById('node-detail');
    const contentEl = document.getElementById('node-detail-content');
    if (!detailEl || !contentEl || !edgeData) return;

    const fromNode = visNetworkInstance ? visNetworkInstance.body.data.nodes.get(edgeData.from) : null;
    const toNode = visNetworkInstance ? visNetworkInstance.body.data.nodes.get(edgeData.to) : null;
    currentEdgeEditorState = {
        relationId: edgeData._relation_id || edgeId,
        sourceId: edgeData.from,
        targetId: edgeData.to
    };
    currentNodeEditorState = null;

    let html = '';
    html += `<div style="display:grid;gap:10px;">`;
    html += `<div><strong>关系 ID:</strong> <span style="font-size:12px;color:#666;">${escapeHtml(edgeData._relation_id || edgeId)}</span></div>`;
    html += `<div><strong>源节点:</strong> ${escapeHtml((fromNode && fromNode.label) || edgeData.from)}</div>`;
    html += `<div><strong>目标节点:</strong> ${escapeHtml((toNode && toNode.label) || edgeData.to)}</div>`;
    html += `<label style="font-weight:600;">关系类型</label>`;
    html += `<input id="edge-edit-type" type="text" value="${escapeHtml(edgeData._type || edgeData.label || 'related')}" style="padding:8px 10px;border:1px solid #ddd;border-radius:6px;">`;
    html += `<label style="font-weight:600;">关系说明</label>`;
    html += `<textarea id="edge-edit-description" style="min-height:120px;padding:10px;border:1px solid #ddd;border-radius:6px;line-height:1.5;">${escapeHtml(edgeData._description || '')}</textarea>`;
    html += `<div style="display:flex;gap:8px;justify-content:flex-end;">`;
    html += `<button onclick="saveCurrentEdgeEdit()" class="btn btn-primary">保存关系</button>`;
    html += `</div>`;
    html += `</div>`;

    contentEl.innerHTML = html;
    detailEl.classList.remove('hidden');
}

async function saveCurrentNodeEdit() {
    if (!currentNodeEditorState) return;
    const labelInput = document.getElementById('node-edit-label');
    const contentInput = document.getElementById('node-edit-content');
    const metadata = Object.assign({}, currentNodeEditorState.metadata || {});
    metadata.label = labelInput ? labelInput.value.trim() : metadata.label;

    try {
        const response = await callMaintenanceAPI('/update-node', 'PUT', {
            node_id: currentNodeEditorState.nodeId,
            content: contentInput ? contentInput.value : '',
            metadata: metadata
        });
        if (response.success) {
            showToast('节点已更新', 'success');
            await updateKnowledgeGraph();
            closeNodeDetail();
        }
    } catch (error) {
        console.error('更新节点失败:', error);
        showToast('节点更新失败', 'error');
    }
}

async function saveCurrentEdgeEdit() {
    if (!currentEdgeEditorState) return;
    const typeInput = document.getElementById('edge-edit-type');
    const descInput = document.getElementById('edge-edit-description');
    try {
        const response = await callMaintenanceAPI('/update-relation', 'PUT', {
            relation_id: currentEdgeEditorState.relationId,
            source_id: currentEdgeEditorState.sourceId,
            target_id: currentEdgeEditorState.targetId,
            relation_type: typeInput ? typeInput.value.trim() : 'related',
            metadata: {
                description: descInput ? descInput.value : ''
            }
        });
        if (response.success) {
            showToast('关系已更新', 'success');
            await updateKnowledgeGraph();
            closeNodeDetail();
        }
    } catch (error) {
        console.error('更新关系失败:', error);
        showToast('关系更新失败', 'error');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeJsString(text) {
    return String(text || '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\r/g, '')
        .replace(/\n/g, '\\n');
}

function cleanLatex(text) {
    if (!text) return '';
    text = text.replace(/\[\[(?:TABLE|FORMULA|SEE_TABLE|SEE_FORMULA):[^\]]*\]\]/g, '');
    text = text.replace(/\s{2,}/g, ' ').trim();
    return text;
}

// Convert LaTeX to readable plain text (for node labels on graph)
function latexToText(text) {
    if (!text) return '';
    // Display math $$ ... $$ 鈫?[Formula]
    text = text.replace(/\$\$[\s\S]*?\$\$/g, '[Formula]');
    // Inline math $ ... $ 鈫?readable unicode
    text = text.replace(/\$([^$]+)\$/g, function(m, inner) {
        return simplifyLatex(inner);
    });
    // Clean leftover commands
    text = text.replace(/\\[a-zA-Z]+\{([^}]*)\}/g, '$1');
    text = text.replace(/\\[a-zA-Z]+/g, '');
    text = text.replace(/\{([^}]*)\}/g, '$1');
    text = text.replace(/\s{2,}/g, ' ').trim();
    return text;
}

function simplifyLatex(s) {
    s = s.replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, '($1/$2)');
    s = s.replace(/\\overline\{([^}]*)\}/g, '$1虆');
    s = s.replace(/\\bar\{([^}]*)\}/g, '$1虆');
    s = s.replace(/\\hat\{([^}]*)\}/g, '$1虃');
    s = s.replace(/\\tilde\{([^}]*)\}/g, '$1虄');
    s = s.replace(/\\dot\{([^}]*)\}/g, '$1虈');
    s = s.replace(/\\left/g, '');
    s = s.replace(/\\right/g, '');
    s = s.replace(/\\partial/g, '∂');
    s = s.replace(/\\sigma/g, '蟽');
    s = s.replace(/\\mu/g, '渭');
    s = s.replace(/\\delta/g, '未');
    s = s.replace(/\\Delta/g, '螖');
    s = s.replace(/\\alpha/g, '伪');
    s = s.replace(/\\beta/g, '尾');
    s = s.replace(/\\gamma/g, '纬');
    s = s.replace(/\\omega/g, '蠅');
    s = s.replace(/\\lambda/g, '位');
    s = s.replace(/\\pi/g, '蟺');
    s = s.replace(/\\theta/g, '胃');
    s = s.replace(/\\epsilon/g, '蔚');
    s = s.replace(/\\rho/g, '蟻');
    s = s.replace(/\\phi/g, '蠁');
    s = s.replace(/\\tau/g, '蟿');
    s = s.replace(/\\sum/g, '∑');
    s = s.replace(/\\prod/g, '∏');
    s = s.replace(/\\sqrt\{([^}]*)\}/g, '鈭?$1)');
    s = s.replace(/\\infty/g, '∞');
    s = s.replace(/\\neq/g, '≠');
    s = s.replace(/\\leq/g, '≤');
    s = s.replace(/\\geq/g, '≥');
    s = s.replace(/\\approx/g, '≈');
    s = s.replace(/\\times/g, '脳');
    s = s.replace(/\\cdot/g, '路');
    s = s.replace(/\\rightarrow/g, '→');
    s = s.replace(/\\Rightarrow/g, '⇒');
    s = s.replace(/\\operatorname\{([^}]*)\}/g, '$1');
    s = s.replace(/\\text\{([^}]*)\}/g, '$1');
    s = s.replace(/_{([^}]*)}/g, function(m, inner) {
        return String.fromCharCode(0x2080) + inner;
    });
    s = s.replace(/\^{([^}]*)}/g, '^$1');
    s = s.replace(/\\[a-zA-Z]+/g, '');
    s = s.replace(/\{([^}]*)\}/g, '$1');
    s = s.replace(/\s+/g, ' ').trim();
    return s;
}

// Render text with LaTeX to HTML using KaTeX (for detail panel)
function renderLatexContent(text) {
    if (!text) return '';
    var escaped = '';
    for (var i = 0; i < text.length; i++) {
        var ch = text[i];
        if (ch === '<') escaped += '&lt;';
        else if (ch === '>') escaped += '&gt;';
        else if (ch === '&') escaped += '&amp;';
        else escaped += ch;
    }

    if (typeof katex === 'undefined') {
        return escaped;
    }

    var parts = [];
    var regex = /\$\$([\s\S]*?)\$\$|\$([^$]+)\$/g;
    var lastIdx = 0;
    var match;
    while ((match = regex.exec(escaped)) !== null) {
        if (match.index > lastIdx) {
            parts.push({ type: 'text', content: escaped.substring(lastIdx, match.index) });
        }
        if (match[1] !== undefined) {
            parts.push({ type: 'display', content: match[1] });
        } else {
            parts.push({ type: 'inline', content: match[2] });
        }
        lastIdx = regex.lastIndex;
    }
    if (lastIdx < escaped.length) {
        parts.push({ type: 'text', content: escaped.substring(lastIdx) });
    }

    if (parts.length === 0 || (parts.length === 1 && parts[0].type === 'text')) {
        return escaped;
    }

    var result = '';
    for (var j = 0; j < parts.length; j++) {
        var p = parts[j];
        if (p.type === 'text') {
            result += p.content;
        } else {
            try {
                result += katex.renderToString(p.content.trim(), {
                    displayMode: (p.type === 'display'),
                    throwOnError: false,
                    trust: true
                });
            } catch (e) {
                result += '<code style="background:#f5f5f5;padding:2px 4px;border-radius:3px;">' +
                    (p.type === 'display' ? '$$' : '$') + p.content + (p.type === 'display' ? '$$' : '$') +
                    '</code>';
            }
        }
    }
    return result;
}

function displayContent(text) {
    return renderLatexContent(text);
}

function getLocalChapterEntries() {
    var entries = [];
    var seen = {};
    function pushEntry(title) {
        var normalizedTitle = String(title || '').trim();
        if (!normalizedTitle || seen[normalizedTitle]) return;
        seen[normalizedTitle] = true;
        entries.push({
            id: 'chapter_' + normalizedTitle,
            title: normalizedTitle,
            source: 'local'
        });
    }

    try {
        var index = JSON.parse(localStorage.getItem('chapterIndex') || '[]');
        index.forEach(function(title) {
            pushEntry(title);
        });
    } catch (e) {
        console.warn('localStorage chapters unavailable:', e);
    }

    if (typeof localStorage.length === 'number' && typeof localStorage.key === 'function') {
        for (var i = 0; i < localStorage.length; i++) {
            var storageKey = localStorage.key(i);
            if (!storageKey || !storageKey.startsWith('chapter_')) continue;
            try {
                var stored = JSON.parse(localStorage.getItem(storageKey) || '{}');
                pushEntry(stored.title || storageKey.substring('chapter_'.length));
            } catch (e) {
                pushEntry(storageKey.substring('chapter_'.length));
            }
        }
    }

    return entries;
}

async function loadChapterCache() {
    if (!chapterCachePromise) {
        chapterCachePromise = fetch(`chapters-cache.json?ts=${Date.now()}`)
            .then(function(response) {
                if (!response.ok) {
                    throw new Error('chapter cache not available');
                }
                return response.json();
            })
            .catch(function(error) {
                console.warn('Chapter cache unavailable:', error);
                return { chapters: {} };
            });
    }
    return chapterCachePromise;
}

function getCachedChapterRecords(payload) {
    var chapters = payload && payload.chapters;
    if (!chapters || typeof chapters !== 'object') return [];
    return Object.values(chapters).filter(function(chapter) {
        return chapter && typeof chapter === 'object' && chapter.id && chapter.title;
    });
}

// 鍔犺浇宸蹭繚瀛樼殑绔犺妭鍒楄〃
async function loadSavedChapterList() {
    var requestToken = ++savedChapterListRequestToken;
    var select = document.getElementById('saved-chapter-select');
    var listPanel = document.getElementById('chapter-list-panel');
    var localEntries = getLocalChapterEntries();
    var localTitles = localEntries.map(function(entry) { return entry.title; });
    if (!select) return;
    select.innerHTML = '<option value="">-- 请选择已保存的章节 --</option>';

    localEntries.forEach(function(entry) {
        var option = document.createElement('option');
        option.value = entry.id;
        option.textContent = entry.title + ' (本地)';
        option.dataset.source = entry.source;
        select.appendChild(option);
    });

    
    try {
        var response = await callAPI('/list-chapters', 'GET');
        if (requestToken !== savedChapterListRequestToken) return;
        if (response.success && response.chapters) {
            response.chapters.forEach(function(chapter) {
                
                if (localTitles.indexOf(chapter.title) !== -1) return;
                var option = document.createElement('option');
                option.value = chapter.id;
                option.textContent = chapter.title;
                option.dataset.source = 'api';
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.warn('Backend chapters unavailable:', error);
    }

    if (requestToken !== savedChapterListRequestToken) return;
    try {
        var cachePayload = await loadChapterCache();
        if (requestToken !== savedChapterListRequestToken) return;
        getCachedChapterRecords(cachePayload).forEach(function(chapter) {
            if (localTitles.indexOf(chapter.title) !== -1) return;
            var exists = Array.from(select.options).some(function(option) {
                return option.value === chapter.id || option.textContent === chapter.title;
            });
            if (exists) return;
            var option = document.createElement('option');
            option.value = chapter.id;
            option.textContent = chapter.title;
            option.dataset.source = 'cache';
            select.appendChild(option);
        });
    } catch (error) {
        console.warn('Chapter cache unavailable:', error);
    }

    
    if (listPanel && listPanel.style.display !== 'none') {
        refreshChapterListContent();
    }
}

// 鍔犺浇宸蹭繚瀛樼殑绔犺妭
async function loadSavedChapter() {
    const select = document.getElementById('saved-chapter-select');
    const chapterId = select.value;

    if (!chapterId) {
        document.getElementById('selected-chapter-info').style.display = 'none';
        currentChapter = null;
        return;
    }

    if (chapterId.startsWith('chapter_')) {
        try {
            const stored = JSON.parse(localStorage.getItem(chapterId) || '{}');
            if (stored.title) {
                currentChapter = {
                    id: chapterId,
                    title: stored.title,
                    content: stored.lecture || ''
                };

                const infoPanel = document.getElementById('selected-chapter-info');
                document.getElementById('chapter-info-title').textContent = stored.title;
                document.getElementById('chapter-info-time').textContent = stored.updatedAt || '未知';
                document.getElementById('chapter-info-lecture-status').textContent = stored.lecture ? '已生成' : '未生成';
                infoPanel.style.display = 'block';

                document.getElementById('lecture-note').value = stored.lecture || '';
                const floatNote = document.getElementById('lecture-note-float');
                if (floatNote) {
                    floatNote.value = stored.lecture || '';
                }

                showToast(`已加载本地章节 "${stored.title}"`, 'info');
                await updateKnowledgeGraph();
                return;
            }
        } catch (error) {
            console.error('读取本地章节失败:', error);
            showToast('读取本地章节失败', 'error');
            return;
        }
    }

    try {
        const response = await callAPI(`/get-chapter?chapter_id=${chapterId}`, 'GET');
        if (response.success && response.chapter) {
            const chapter = response.chapter;

            currentChapter = {
                id: chapter.id,
                title: chapter.title,
                content: chapter.content
            };

            
            const infoPanel = document.getElementById('selected-chapter-info');
            document.getElementById('chapter-info-title').textContent = chapter.title;
            document.getElementById('chapter-info-time').textContent = chapter.created_at || '未知';
            document.getElementById('chapter-info-lecture-status').textContent = chapter.lecture_content ? '已生成' : '未生成';
            infoPanel.style.display = 'block';

            if (chapter.lecture_content) {
                document.getElementById('lecture-note').value = chapter.lecture_content;
                const floatNote = document.getElementById('lecture-note-float');
                if (floatNote) {
                    floatNote.value = chapter.lecture_content;
                }
                showToast(`已加载章节 "${chapter.title}" 的授课文稿`, 'info');
            } else {
                document.getElementById('lecture-note').value = '';
                showToast(`已加载章节 "${chapter.title}"`, 'info');
            }
            await updateKnowledgeGraph();
        } else {
            throw new Error('chapter not found in API');
        }
    } catch (error) {
        console.error('加载章节失败:', error);
        try {
            const cachePayload = await loadChapterCache();
            const cachedChapter = getCachedChapterRecords(cachePayload).find(function(chapter) {
                return chapter.id === chapterId;
            });
            if (cachedChapter) {
                currentChapter = {
                    id: cachedChapter.id,
                    title: cachedChapter.title,
                    content: cachedChapter.content || ''
                };
                const infoPanel = document.getElementById('selected-chapter-info');
                document.getElementById('chapter-info-title').textContent = cachedChapter.title;
                document.getElementById('chapter-info-time').textContent = cachedChapter.updated_at || cachedChapter.created_at || '未知';
                document.getElementById('chapter-info-lecture-status').textContent = cachedChapter.lecture_content ? '已生成' : '未生成';
                infoPanel.style.display = 'block';
                document.getElementById('lecture-note').value = cachedChapter.lecture_content || '';
                const floatNote = document.getElementById('lecture-note-float');
                if (floatNote) {
                    floatNote.value = cachedChapter.lecture_content || '';
                }
                showToast(`已从缓存加载章节 "${cachedChapter.title}"`, 'info');
                await updateKnowledgeGraph();
                return;
            }
        } catch (cacheError) {
            console.error('读取章节缓存失败:', cacheError);
        }
        showToast('加载章节失败', 'error');
    }
}

// 鐢熸垚鎺堣鏂囨
async function generateLecture() {
    if (!currentChapter) {
        showToast('请先选择章节');
        return;
    }

    await generateLectureWithAPI(currentChapter);
}

// ==================== 鍔犺浇绔犺妭鏁版嵁 ====================

async function loadChapterData(chapterId) {
    if (!chapterId) return;

    try {
        const response = await callAPI(`/get-chapter?chapter_id=${chapterId}`, 'GET');
        if (response.success && response.chapter) {
            const chapter = response.chapter;
            currentChapter = chapter;

            
            if (chapter.lecture_content) {
                document.getElementById('lecture-note').value = chapter.lecture_content;
                const floatNote = document.getElementById('lecture-note-float');
                if (floatNote) {
                    floatNote.value = chapter.lecture_content;
                }
                showToast(`已加载章节 "${chapter.title}" 的保存内容`, 'info');
            } else {
                // 娌℃湁淇濆瓨鐨勬枃妗堬紝鐢熸垚鏂扮殑
                generateLectureWithAPI(chapter);
            }

            // 教师端图谱统一从 vector_index_system 后端加载，避免旧章节缓存覆盖新版图谱。
            await updateKnowledgeGraph();
        }
    } catch (error) {
        console.error('加载章节数据失败:', error);
    }
}

// ==================== 瀵煎叆鎺堣鏂囨鍔熻兘 ====================

async function importLecture() {
    const note = document.getElementById('lecture-note').value;

    if (!note) {
        showToast('请先生成授课文案');
        return;
    }

    if (!currentChapter || !currentChapter.id) {
        showToast('请先导入或选择章节');
        return;
    }

    try {
        
        const response = await callAPI('/save-lecture', 'POST', {
            chapter_id: currentChapter.id,
            lecture_content: note
        });

        if (response.success) {
            showToast('授课文案已导入并保存，可在授课模式查看', 'success');
            // 鍒锋柊绔犺妭鍒楄〃
            loadChapterList();
        } else {
            throw new Error(response.error || '保存失败');
        }
    } catch (error) {
        console.error('导入授课文案失败:', error);
        showToast('授课文案已保存到本地', 'success');
    }
}

async function saveLecture() {
    const note = document.getElementById('lecture-note').value;
    if (!note) {
        showToast('没有可保存的授课文案', 'warning');
        return;
    }

    const titleInput = document.getElementById('chapter-title');
    var chapterTitle = titleInput ? titleInput.value.trim() : '';
    if (!chapterTitle && currentChapter) chapterTitle = currentChapter.title || '';
    if (!chapterTitle) {
        showToast('请先输入章节名称', 'warning');
        return;
    }

    saveToLocal(chapterTitle, 'lecture', note);
    showToast('文稿已保存到: ' + chapterTitle, 'success');
    await refreshTeacherChapterSelectors('chapter_' + chapterTitle);

    const chapterId = (currentChapter && currentChapter.id) ? currentChapter.id : 'chapter_' + chapterTitle;

    // 保存文稿只更新 lecture_content，不重导图谱，也不覆盖章节正文。
    callAPI('/save-lecture', 'POST', {
        chapter_id: chapterId,
        lecture_content: note
    }).catch(function() {});
}

async function saveGraph() {
    if (!visNetworkInstance) {
        showToast('没有可保存的图谱', 'warning');
        return;
    }

    var titleInput = document.getElementById('chapter-title');
    var chapterTitle = titleInput ? titleInput.value.trim() : '';
    if (!chapterTitle && currentChapter) chapterTitle = currentChapter.title || '';
    if (!chapterTitle) {
        showToast('请先输入章节名称', 'warning');
        return;
    }

    var nodes = visNetworkInstance.body.data.nodes.get();
    var edges = visNetworkInstance.body.data.edges.get();
    var graphSaveData = {
        nodes: nodes.map(function(n) {
            return {
                id: n.id, label: n.label, type: n._type || '',
                color: n.color || '',
                _type: n._type || '',
                _full_label: n._full_label || '',
                _content: n._content || ''
            };
        }),
        edges: edges.map(function(e) { return { from: e.from, to: e.to, label: e.label || '' }; })
    };

    saveToLocal(chapterTitle, 'graph', graphSaveData);
    showToast('图谱已保存到: ' + chapterTitle, 'success');
    await refreshTeacherChapterSelectors('chapter_' + chapterTitle);

    // 鍚屾椂灏濊瘯淇濆瓨鍒板悗绔紙涓嶉樆濉烇級
    callAPI('/save-chapter', 'POST', {
        title: chapterTitle,
        graph_data: graphSaveData
    }).catch(function() {});
}

function saveToLocal(chapterTitle, type, data) {
    var key = 'chapter_' + chapterTitle;
    var stored = {};
    try { stored = JSON.parse(localStorage.getItem(key) || '{}'); } catch(e) {}
    stored.title = chapterTitle;
    stored[type] = data;
    stored.updatedAt = new Date().toISOString();
    localStorage.setItem(key, JSON.stringify(stored));

    // Update chapter index
    var index = [];
    try { index = JSON.parse(localStorage.getItem('chapterIndex') || '[]'); } catch(e) {}
    if (index.indexOf(chapterTitle) === -1) index.push(chapterTitle);
    localStorage.setItem('chapterIndex', JSON.stringify(index));

    currentChapter = { id: key, title: chapterTitle };
}

async function refreshTeacherChapterSelectors(savedChapterId) {
    await loadSavedChapterList();
    loadLectureChapterList();

    if (savedChapterId) {
        var savedSelect = document.getElementById('saved-chapter-select');
        if (savedSelect) {
            savedSelect.value = savedChapterId;
            await loadSavedChapter();
        }
    }
}

function toggleChapterList() {
    var panel = document.getElementById('chapter-list-panel');
    if (!panel) return;
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        refreshChapterListContent();
    } else {
        panel.style.display = 'none';
    }
}

function refreshChapterListContent() {
    var requestToken = ++chapterListContentRequestToken;
    var container = document.getElementById('chapter-list-content');
    if (!container) return;
    container.innerHTML = '';

    var chapters = getLocalChapterEntries().map(function(entry) {
        return { title: entry.title, source: entry.source, id: entry.id };
    });

    // 绔嬪嵆娓叉煋鏈湴绔犺妭
    renderChapterListItems(container, chapters);

    // 2. 鍐嶅皾璇曚粠鍚庣 API 琛ュ厖锛堝紓姝ワ級
    callAPI('/list-chapters', 'GET').then(function(resp) {
        if (requestToken !== chapterListContentRequestToken) return;
        if (resp.success && resp.chapters) {
            resp.chapters.forEach(function(ch) {
                var exists = chapters.some(function(c) { return c.title === ch.title; });
                if (!exists) {
                    chapters.push({ title: ch.title, source: 'api', id: ch.id });
                }
            });
        }
        container.innerHTML = '';
        renderChapterListItems(container, chapters);
    }).catch(function() {});

    loadChapterCache().then(function(cachePayload) {
        if (requestToken !== chapterListContentRequestToken) return;
        getCachedChapterRecords(cachePayload).forEach(function(chapter) {
            var exists = chapters.some(function(c) { return c.title === chapter.title; });
            if (!exists) {
                chapters.push({ title: chapter.title, source: 'cache', id: chapter.id });
            }
        });
        container.innerHTML = '';
        renderChapterListItems(container, chapters);
    }).catch(function() {});
}

function renderChapterListItems(container, chapters) {
    if (chapters.length === 0) {
        container.innerHTML = '<div style="padding:12px; color:#999; text-align:center; font-size:13px;">暂无已保存章节</div>';
        return;
    }
    chapters.forEach(function(ch) {
        var row = document.createElement('div');
        row.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:8px 14px; border-bottom:1px solid #eee; font-size:13px;';
        var label = document.createElement('span');
        label.textContent = ch.title + (ch.source === 'local' ? ' (本地)' : '');
        label.style.cssText = 'flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
        var delBtn = document.createElement('button');
        delBtn.textContent = '删除';
        delBtn.className = 'btn btn-small';
        delBtn.style.cssText = 'margin-left:10px; padding:3px 10px; font-size:12px; color:#e74c3c; border-color:#e74c3c;';
        delBtn.onclick = function() { deleteChapter(ch.title, ch.source, ch.id); };
        row.appendChild(label);
        row.appendChild(delBtn);
        container.appendChild(row);
    });
}

function deleteChapter(title, source, chapterId) {
    if (!confirm('纭畾瑕佸垹闄ょ珷鑺?"' + title + '" 鍚楋紵')) return;

    
    if (source === 'local' || source === 'api') {
        localStorage.removeItem('chapter_' + title);
        var index = [];
        try { index = JSON.parse(localStorage.getItem('chapterIndex') || '[]'); } catch(e) {}
        index = index.filter(function(t) { return t !== title; });
        localStorage.setItem('chapterIndex', JSON.stringify(index));
    }

    // Also delete the server-side chapter when needed.
    if (source === 'api' && chapterId) {
        callAPI('/delete-chapter', 'POST', { chapter_id: chapterId }).catch(function() {
            console.warn('Backend delete failed for:', title);
        });
    }

    showToast('已删除 ' + title, 'success');
    refreshChapterListContent();
    loadSavedChapterList();
}

function clearLecture() {
    const note = document.getElementById('lecture-note').value;

    if (!note) {
        showToast('Lecture is already empty', 'info');
        return;
    }

    if (confirm('Clear the lecture content?')) {
        document.getElementById('lecture-note').value = '';
        const floatNote = document.getElementById('lecture-note-float');
        if (floatNote) {
            floatNote.value = '';
        }
        showToast('Lecture cleared', 'info');
    }
}


// ==================== 鎺堣鏂囨娴獥鍒囨崲 ====================

function toggleLectureFloat() {
    const lectureFloat = document.getElementById('lecture-float-window');
    if (lectureFloat) {
        if (lectureFloat.classList.contains('hidden')) {
            lectureFloat.classList.remove('hidden');
        } else {
            lectureFloat.classList.add('hidden');
        }
    }
}

function syncFloatToMain() {
    const floatNote = document.getElementById('lecture-note-float');
    const mainNote = document.getElementById('lecture-note');

    if (floatNote && mainNote) {
        mainNote.value = floatNote.value;
        showToast('Float content synced to main editor', 'success');
    }
}

function syncMainToFloat() {
    const floatNote = document.getElementById('lecture-note-float');
    const mainNote = document.getElementById('lecture-note');

    if (floatNote && mainNote) {
        floatNote.value = mainNote.value;
        showToast('Main editor synced to float window', 'success');
    }
}

function refreshLectureFloat() {
    
    const floatNote = document.getElementById('lecture-note-float');
    const mainNote = document.getElementById('lecture-note');

    if (floatNote && mainNote) {
        floatNote.value = mainNote.value;
        showToast('Float content refreshed', 'info');
    }
}

function loadLectureFromFloat() {
    syncFloatToMain();
}

function editLectureInFloat() {
    const floatNote = document.getElementById('lecture-note-float');
    if (floatNote) {
        floatNote.readOnly = false;
        floatNote.focus();
    }
}

function closeRecordHistoryModal() {
    const modal = document.getElementById('record-history-modal');
    modal.classList.add('hidden');
}

function showRecordHistory() {
    const modal = document.getElementById('record-history-modal');
    const historyList = document.getElementById('record-history-list');

    if (lectureRecords.length === 0) {
        historyList.innerHTML = '<p class="placeholder">暂无授课记录</p>';
    } else {
        let html = '';
        lectureRecords.forEach((record, index) => {
            html += `
                <div class="record-item" onclick="loadLectureRecord('${record.id}')">
                    <div class="record-header">
                        <span class="record-title">${record.chapterTitle}</span>
                        <span class="record-time">${record.savedAt}</span>
                    </div>
                    <div class="record-progress">杩涘害锛?{record.progress.toFixed(1)}%</div>
                    <div class="record-position">浣嶇疆锛氱${record.position}瀛楃</div>
                </div>
            `;
        });
        historyList.innerHTML = html;
    }

    modal.classList.remove('hidden');
}

// ==================== AI鑷劧琛ュ厖鍔熻兘 ====================

function aiNaturalSupplement(originalText, supplement) {
        const sentences = originalText.split(/[銆傦紒锛焅n]/).filter(s => s.trim());

    if (sentences.length === 0) {
                return supplement;
    }

    
    const hasNumber = /\d+/.test(supplement); 
    const hasContrast = /但是|不过|然而/.test(supplement);
    const hasConnection = /和|与|以及|同时/.test(supplement);
    
    let transition = '';

    if (hasConnection) {
        // 骞跺垪鍏崇郴锛屼娇鐢?姝ゅ"
        transition = '此外，';
    } else if (hasContrast) {
        // 杞姌鍏崇郴锛屼娇鐢?涓嶈繃"
        transition = '不过，';
    } else if (hasNumber) {
        // 鏈夌紪鍙峰唴瀹癸紝浣跨敤"鎺ヤ笅鏉?
        transition = '鎺ヤ笅鏉ワ紝';
    } else {
        // 涓€鑸ˉ鍏咃紝浣跨敤"鍙﹀"
        transition = '另外，';
    }

        const insertIndex = Math.min(Math.floor(sentences.length * 0.7), sentences.length - 1);

    
    let result = sentences.slice(0, insertIndex).join('。');

    if (sentences.slice(0, insertIndex).length > 0) {
        if (result && !result.endsWith('。') && !result.endsWith('？') && !result.endsWith('！')) {
            result += '。';
        }
        // 娣诲姞杩囨浮璇嶅拰琛ュ厖鍐呭
        result += transition + supplement;
    } else {
        return supplement;
    }

    
    const remainingSentences = sentences.slice(insertIndex);
    if (remainingSentences.length > 0) {
        result += remainingSentences.join('。');
        if (!result.endsWith('。') && !result.endsWith('？') && !result.endsWith('！')) {
            result += '。';
        }
    }

    return result;
}

async function confirmSupplement() {
    const supplement = document.getElementById('supplement-content').value;

    if (!supplement) {
        showToast('请输入或确认补充内容');
        return;
    }

    
    const currentNote = document.getElementById('lecture-note').value;

    try {
        // 璋冪敤鍚庣API杩涜鑷劧琛ュ厖
        showToast('正在处理补充内容...', 'info');
        const updatedNote = await naturalSupplementWithAPI(currentNote, supplement);

        document.getElementById('lecture-note').value = updatedNote;

                const floatNote = document.getElementById('lecture-note-float');
        if (floatNote) {
            floatNote.value = updatedNote;
        }

        // 鏇存柊鐭ヨ瘑鍥捐氨
        updateKnowledgeGraph();

        showToast('补充内容已自然融入授课文案', 'success');
    } catch (error) {
        console.error('鑷劧琛ュ厖澶辫触:', error);
                const updatedNote = aiNaturalSupplement(currentNote, supplement);
        document.getElementById('lecture-note').value = updatedNote;
        const floatNote = document.getElementById('lecture-note-float');
        if (floatNote) {
            floatNote.value = updatedNote;
        }
        updateKnowledgeGraph();
        showToast('Supplement added in local mode', 'warning');
    }

    // 鍏抽棴琛ュ厖鍗＄墖
    document.getElementById('supplement-card').classList.add('hidden');
    document.getElementById('supplement-content').value = '';

    if (isLecturing) {
        const pauseBtn = document.getElementById('btn-pause-lecture');
        pauseBtn.textContent = '继续授课';
        pauseBtn.onclick = resumeLecture;
    }
}



let isContextMenuShown = false;



let recognition = null;
let isRecognizing = false;

function initVoiceRecognition() {
    
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        console.log('娴忚鍣ㄤ笉鏀寔璇煶璇嗗埆');
        return false;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = 'zh-CN';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = function(event) {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        
        const resultTextarea = document.getElementById('voice-recognized-text');
        if (resultTextarea) {
            const currentText = resultTextarea.value;
            if (finalTranscript) {
                resultTextarea.value = currentText + finalTranscript;
            }
            document.getElementById('record-status-text').textContent =
                interimTranscript ? '姝ｅ湪璇嗗埆: ' + interimTranscript : '姝ｅ湪褰曢煶...';
        }
    };

    recognition.onerror = function(event) {
        console.error('璇煶璇嗗埆閿欒:', event.error);
        const statusText = document.getElementById('record-status-text');
        if (statusText) {
            statusText.textContent = '识别错误: ' + event.error;
        }
        stopVoiceRecognition();
    };

    recognition.onend = function() {
        if (isRecognizing) {
            // 濡傛灉鏄嚜鍔ㄥ仠姝絾鐢ㄦ埛鎯崇户缁紝閲嶆柊寮€濮?            recognition.start();
        } else {
            const statusText = document.getElementById('record-status-text');
            if (statusText) {
                statusText.textContent = 'Recording stopped';
            }
            document.getElementById('btn-start-record').disabled = false;
            document.getElementById('btn-stop-record').disabled = true;
        }
    };

    return true;
}

function openVoiceRecord() {
    const voiceWindow = document.getElementById('voice-record-window');
    voiceWindow.classList.remove('hidden');

    if (!recognition && !initVoiceRecognition()) {
        showToast('Speech recognition is not supported in this browser', 'error');
        document.getElementById('record-status-text').textContent = '浏览器不支持语音识别';
    }

    document.getElementById('voice-recognized-text').value = '';
    document.getElementById('record-status-text').textContent = '准备开始录音...';
}

function startVoiceRecord() {
    if (!recognition) {
        if (!initVoiceRecognition()) {
            showToast('Failed to initialize speech recognition', 'error');
            return;
        }
    }

    isRecognizing = true;
    recognition.start();

    document.getElementById('btn-start-record').disabled = true;
    document.getElementById('btn-stop-record').disabled = false;
    document.getElementById('record-status-text').textContent = '正在录音...';
    showToast('Recording started', 'info');
}

function stopVoiceRecord() {
    isRecognizing = false;
    if (recognition) {
        recognition.stop();
    }
    document.getElementById('record-status-text').textContent = 'Recording stopped';
    showToast('Recording stopped', 'info');
}

function closeVoiceRecord() {
    isRecognizing = false;
    if (recognition) {
        recognition.stop();
    }
    document.getElementById('voice-record-window').classList.add('hidden');
}

function confirmVoiceContent() {
    const voiceText = document.getElementById('voice-recognized-text').value;
    if (!voiceText) {
        showToast('没有识别到内容');
        return;
    }

    // 灏嗚闊宠瘑鍒唴瀹规坊鍔犲埌琛ュ厖鍐呭妗?    document.getElementById('supplement-content').value = voiceText;

    // 鍏抽棴璇煶璇嗗埆绐楀彛
    closeVoiceRecord();

    
    const supplementCard = document.getElementById('supplement-card');
    if (supplementCard) {
        supplementCard.classList.remove('hidden');
    }

    showToast('Voice content added to supplement', 'success');
}

function saveVoiceDraft() {
    const voiceText = document.getElementById('voice-recognized-text').value;
    if (!voiceText) {
        showToast('没有可保存的内容');
        return;
    }

    supplementDrafts.push({
        id: 'draft_' + Date.now(),
        content: voiceText,
        time: new Date().toLocaleString()
    });

    renderDraftList();
    showToast('已保存为草稿', 'success');
    closeVoiceRecord();
}

function discardVoiceContent() {
    document.getElementById('voice-recognized-text').value = '';
    showToast('Voice content discarded', 'info');
}

function renderDraftList() {
    const draftList = document.getElementById('draft-list');
    if (!draftList) return;

    if (supplementDrafts.length === 0) {
        draftList.innerHTML = '<p class="placeholder">暂无草稿</p>';
        return;
    }

    let html = '';
    supplementDrafts.forEach((draft, index) => {
        html += `
            <div class="draft-item">
                <div class="draft-content">${draft.content.substring(0, 50)}...</div>
                <div class="draft-time">${draft.time}</div>
                <div class="draft-actions">
                    <button onclick="loadDraft(${index})" class="btn btn-small">鍔犺浇</button>
                    <button onclick="deleteDraft(${index})" class="btn btn-small btn-danger">鍒犻櫎</button>
                </div>
            </div>
        `;
    });
    draftList.innerHTML = html;
}

function loadDraft(index) {
    const draft = supplementDrafts[index];
    document.getElementById('supplement-content').value = draft.content;
    // 纭繚琛ュ厖鍗＄墖鏄墦寮€鐨?    document.getElementById('supplement-card').classList.remove('hidden');
    document.getElementById('supplement-content').focus();
    showToast('Draft loaded', 'success');
}

function deleteDraft(index) {
    supplementDrafts.splice(index, 1);
    renderDraftList();
    showToast('Draft deleted', 'info');
}

function saveDraft() {
    const supplement = document.getElementById('supplement-content').value;
    if (!supplement) {
        showToast('没有可保存的草稿');
        return;
    }

    supplementDrafts.push({
        id: 'draft_' + Date.now(),
        content: supplement,
        time: new Date().toLocaleString()
    });

    renderDraftList();
    document.getElementById('supplement-content').value = '';
    showToast('Draft saved', 'success');
}

// ==================== 璇煶鎾斁鐩稿叧 ====================



const chapterData = {};

// ==================== 绔犺妭閫夋嫨 ====================

function loadLectureChapterList() {
    var requestToken = ++lectureChapterListRequestToken;
    var select = document.getElementById('chapter-select');
    if (!select) return;
    select.innerHTML = '<option value="">-- 请选择章节 --</option>';

    getLocalChapterEntries().forEach(function(entry) {
        var option = document.createElement('option');
        option.value = entry.id;
        option.textContent = entry.title;
        option.dataset.source = entry.source;
        select.appendChild(option);
    });

    // 涔熷皾璇曞悗绔?API
    callAPI('/list-chapters', 'GET').then(function(resp) {
        if (requestToken !== lectureChapterListRequestToken) return;
        if (resp.success && resp.chapters) {
            var existing = [];
            for (var i = 0; i < select.options.length; i++) {
                existing.push(select.options[i].textContent);
            }
            resp.chapters.forEach(function(ch) {
                if (existing.indexOf(ch.title) === -1) {
                    var option = document.createElement('option');
                    option.value = ch.id;
                    option.textContent = ch.title;
                    option.dataset.source = 'api';
                    select.appendChild(option);
                }
            });
        }
    }).catch(function() {});

    loadChapterCache().then(function(cachePayload) {
        if (requestToken !== lectureChapterListRequestToken) return;
        var existing = [];
        for (var i = 0; i < select.options.length; i++) {
            existing.push(select.options[i].textContent);
        }
        getCachedChapterRecords(cachePayload).forEach(function(chapter) {
            if (existing.indexOf(chapter.title) !== -1) return;
            var option = document.createElement('option');
            option.value = chapter.id;
            option.textContent = chapter.title;
            option.dataset.source = 'cache';
            select.appendChild(option);
        });
    }).catch(function() {});
}

function onLectureChapterChange() {
    var select = document.getElementById('chapter-select');
    var val = select.value;
    if (!val) return;

    
    if (val.startsWith('chapter_')) {
        try {
            var stored = JSON.parse(localStorage.getItem(val) || '{}');
            if (stored.title) {
                currentChapter = { id: val, title: stored.title };

                
                if (stored.lecture) {
                    document.getElementById('lecture-note').value = stored.lecture;
                    var floatNote = document.getElementById('lecture-note-float');
                    if (floatNote) floatNote.value = stored.lecture;
                }

                
                showToast('已加载章节 ' + stored.title, 'info');
                updateKnowledgeGraph();
                return;
            }
        } catch(e) {
            console.warn('璇诲彇鏈湴绔犺妭鏁版嵁澶辫触:', e);
        }
    }

    // 鍥為€€鍒?API
    loadChapterData(val);
}

function getSelectedChapter() {
    const select = document.getElementById('chapter-select');
    if (!select) return null;

    const selectedId = select.value;
    if (currentChapter && currentChapter.id === selectedId) {
        return currentChapter;
    }
    return chapterData[selectedId] || null;
}

// ==================== AI鎺堣鍔熻兘 ====================

function startLecture() {
        const selectedChapter = getSelectedChapter();

    if (!selectedChapter) {
        showToast('请先选择授课章节');
        return;
    }

    currentChapter = selectedChapter;

    // 閲嶇疆鎵€鏈夋挱鏀剧姸鎬?    isLecturing = true;
    isPlayingAudio = false;
    currentLecturePosition = 0;
    currentLectureProgress = 0;
    audioStartTime = null;

    // 閲嶇疆鏁欏笀绔挱鏀剧姸鎬?    teacherPlaybackState.isPlaying = false;
    teacherPlaybackState.isPaused = false;
    teacherPlaybackState.currentPosition = 0;
    teacherPlaybackState.showFullContent = false;
    teacherPlaybackState.highlightedNodes.clear();

    

    const btn = document.getElementById('btn-start-lecture');
    btn.textContent = '授课中...';
    btn.disabled = true;

    document.getElementById('btn-pause-lecture').disabled = false;
    document.getElementById('btn-stop-lecture').disabled = false;

    
    const pauseBtn = document.getElementById('btn-pause-lecture');
    pauseBtn.textContent = '暂停补充';
    pauseBtn.onclick = confirmPauseLecture;

    showToast(`开始授课：${currentChapter.title}`, 'success');

    // 鏄剧ず鏁欏笀绔巿璇惧睍绀哄尯鍩?    showTeacherLectureDisplay();

    // 璋冪敤鍚庣API鐢熸垚鎺堣鏂囨
    generateLectureWithAPI(currentChapter);
}

function playAudioText(text) {
    console.log('寮€濮嬫挱鏀鹃煶棰戯紝鏂囨湰闀垮害:', text.length);
        const audioStatus = document.getElementById('audio-status');
    const audioTextEl = document.getElementById('audio-text');
    const statusText = document.getElementById('lecture-status-text');

    if (audioStatus && audioTextEl && statusText) {
        if (isPlayingAudio) {
            console.log('Stopping previous playback');
            stopAudio();
        }

        
        if (audioStatus.dataset.progressInterval) {
            console.log('娓呴櫎閬楃暀鐨刬nterval');
            clearInterval(parseInt(audioStatus.dataset.progressInterval));
            delete audioStatus.dataset.progressInterval;
        }

        isPlayingAudio = true;
        // 鎬绘槸浠庢柊鐨勫紑濮嬫椂闂村紑濮嬶紝涓嶄娇鐢ㄦ殏鍋滄仮澶嶇殑閫昏緫
        audioStartTime = Date.now();
        currentLecturePosition = 0;
        currentLectureProgress = 0;

        audioStatus.classList.remove('hidden');
        audioTextEl.textContent = '正在播放 AI 授课...';
        statusText.textContent = '授课进行中...';

        console.log('寮€濮嬫椂闂?', audioStartTime, '鎾斁鏃堕暱棰勮:', Math.max(5000, text.length / 30 * 1000));

        
        const totalDuration = Math.max(5000, text.length / 30 * 1000);         const updateInterval = 100; 
        const progressInterval = setInterval(() => {
            console.log('interval杩愯涓? isPlayingAudio:', isPlayingAudio);
            if (!isPlayingAudio) {
                console.log('妫€娴嬪埌鏆傚仠锛屾竻闄nterval');
                clearInterval(progressInterval);
                return;
            }

            const elapsed = Date.now() - audioStartTime;
            currentLectureProgress = Math.min(100, (elapsed / totalDuration) * 100);
            currentLecturePosition = Math.floor((elapsed / totalDuration) * text.length);

            audioTextEl.textContent = `播放中... ${currentLectureProgress.toFixed(1)}%`;
            statusText.textContent = `授课进行中... 已播放 ${currentLectureProgress.toFixed(1)}%`;

            
            if (elapsed >= totalDuration) {
                clearInterval(progressInterval);
                audioTextEl.textContent = '播放完成';
                statusText.textContent = '授课文案播放完成';
                isPlayingAudio = false;

                // 鑷姩瀹屾垚鎺堣
                setTimeout(() => {
                    finishLecture();
                }, 2000);
            }
        }, updateInterval);

        // 淇濆瓨interval寮曠敤浠ヤ究鍦ㄥ仠姝㈡椂娓呴櫎
        audioStatus.dataset.progressInterval = progressInterval;
    }
}

function saveLectureRecord() {
    if (!isLecturing) {
        showToast('当前没有进行中的授课');
        return;
    }

    const lectureContent = document.getElementById('lecture-note').value;
    if (!lectureContent) {
        showToast('没有可保存的授课文案');
        return;
    }

    
    const record = {
        id: 'lecture_' + Date.now(),
        chapterId: currentChapter ? currentChapter.id : null,
        chapterTitle: currentChapter ? currentChapter.title : '未命名章节',
        content: lectureContent,
        position: currentLecturePosition,
        progress: currentLectureProgress,
        duration: audioStartTime ? Date.now() - audioStartTime : 0,
        savedAt: new Date().toLocaleString(),
        status: isPlayingAudio ? 'playing' : 'paused'
    };

    // 娣诲姞鍒拌褰曞垪琛?    lectureRecords.push(record);

    showToast(`授课记录已保存，播放位置：${currentLecturePosition} 字符 (${currentLectureProgress.toFixed(1)}%)`, 'success');

    // 鏄剧ず淇濆瓨鐨勮褰?    console.log('淇濆瓨鐨勬巿璇捐褰?', record);
}

function loadLectureRecord(recordId) {
    const record = lectureRecords.find(r => r.id === recordId);
    if (!record) {
        showToast('找不到该授课记录');
        return;
    }

    // 鍔犺浇鎺堣鍐呭
    document.getElementById('lecture-note').value = record.content;

    // 鎭㈠鎾斁浣嶇疆
    currentLecturePosition = record.position;
    currentLectureProgress = record.progress;

    showToast(`已加载授课记录，上次播放到 ${record.progress.toFixed(1)}%`, 'info');
}

function stopAudio() {
    console.log('鍋滄闊抽鎾斁');
    isPlayingAudio = false;
    const audioStatus = document.getElementById('audio-status');
    if (audioStatus) {
        
        if (audioStatus.dataset.progressInterval) {
            const intervalId = parseInt(audioStatus.dataset.progressInterval);
            console.log('娓呴櫎interval:', intervalId);
            clearInterval(intervalId);
            delete audioStatus.dataset.progressInterval;
        }
        audioStatus.classList.add('hidden');
    }
}

function confirmPauseLecture() {
    console.log('纭鏆傚仠鎺堣, isLecturing:', isLecturing, 'isPlayingAudio:', isPlayingAudio);
    if (!isLecturing) {
        showToast('Please start the lecture first', 'warning');
        return;
    }

    // 鍏堣嚜鍔ㄦ殏鍋淎I鎺堣鎾斁
    console.log('璋冪敤stopAudio');
    stopAudio();

    document.getElementById('lecture-status-text').textContent = 'Lecture paused';

    
    const modal = document.getElementById('pause-options-modal');
    modal.classList.remove('hidden');

    console.log('鏆傚仠瀹屾垚');
}

function pauseOnly() {
    // 鍙殏鍋滆闊筹紝涓嶈繘琛岃褰?    stopAudio();

    
    const modal = document.getElementById('pause-options-modal');
    modal.classList.add('hidden');

    document.getElementById('lecture-status-text').textContent = 'Lecture paused';

        const pauseBtn = document.getElementById('btn-pause-lecture');
    pauseBtn.textContent = '继续授课';
    pauseBtn.onclick = resumeLecture;

    showToast('Lecture paused', 'info');
}

function startVoiceRecordFromPause() {
    // 鏆傚仠璇煶骞舵墦寮€褰曢煶
    stopAudio();

    
    const pauseModal = document.getElementById('pause-options-modal');
    pauseModal.classList.add('hidden');

    // 鎵撳紑璇煶璇嗗埆绐楀彛
    openVoiceRecord();
}

function resumeLecture() {
    if (!isLecturing) {
        showToast('Please start the lecture first', 'warning');
        return;
    }

        const currentNote = document.getElementById('lecture-note').value;
    const currentPosition = currentLecturePosition || 0;
    const textFromPosition = currentNote.substring(currentPosition);

    if (textFromPosition && textFromPosition.length > 0) {
        playAudioText(textFromPosition);
    } else {
        showToast('Reached the end of the lecture', 'info');
        finishLecture();
    }

    
    const pauseBtn = document.getElementById('btn-pause-lecture');
    pauseBtn.textContent = '暂停补充';
    pauseBtn.onclick = confirmPauseLecture;

    showToast('继续授课', 'success');
}

function finishLecture() {
    // 鎺堣缁撴潫锛岄噸缃墍鏈夌姸鎬?    isLecturing = false;
    isPlayingAudio = false;
    currentLecturePosition = 0;
    currentLectureProgress = 0;
    audioStartTime = null;

        const btn = document.getElementById('btn-start-lecture');
    btn.textContent = '开始授课';
    btn.disabled = false;

    
    const pauseBtn = document.getElementById('btn-pause-lecture');
    pauseBtn.textContent = '暂停补充';
    pauseBtn.disabled = true;
    pauseBtn.onclick = confirmPauseLecture;

    document.getElementById('btn-stop-lecture').disabled = true;

    // 鍋滄璇煶
    stopAudio();

    document.getElementById('lecture-status-text').textContent = '授课结束';

    
    const supplementCard = document.getElementById('supplement-card');
    if (supplementCard) {
        supplementCard.classList.add('hidden');
    }
}

function stopLecture() {
    if (!isLecturing) {
        showToast('当前没有进行中的授课');
        return;
    }

    // 鍏堣嚜鍔ㄦ殏鍋淎I鎺堣鎾斁
    stopAudio();

    
    const saveModal = document.getElementById('save-record-modal');
    saveModal.classList.remove('hidden');
}

function saveRecordAndExit() {
    // 淇濆瓨鎺堣璁板綍
    saveLectureRecord();

    doExitLecture();
}

function exitWithoutSave() {
    doExitLecture();
}

function closeSaveModal() {
        const saveModal = document.getElementById('save-record-modal');
    saveModal.classList.add('hidden');

        if (isLecturing && isPlayingAudio === false && currentLecturePosition > 0) {
        // 宸茬粡鍦ㄦ殏鍋滅姸鎬侊紝涓嶉渶瑕佸仛棰濆鎿嶄綔
        // 鏆傚仠鎸夐挳搴旇鏄?缁х画鎺堣"
    }
}

function doExitLecture() {
    
    const saveModal = document.getElementById('save-record-modal');
    saveModal.classList.add('hidden');

    isLecturing = false;
    isRecording = false;
    isPlayingAudio = false;

    stopTeacherLecturePlayback();

        const btn = document.getElementById('btn-start-lecture');
    btn.textContent = '开始授课';
    btn.disabled = false;

    
    const pauseBtn = document.getElementById('btn-pause-lecture');
    pauseBtn.textContent = '暂停补充';
    pauseBtn.disabled = true;
    pauseBtn.onclick = confirmPauseLecture;

    document.getElementById('btn-stop-lecture').disabled = true;

    // 鍋滄璇煶
    stopAudio();

    // 閲嶇疆杩涘害
    currentLecturePosition = 0;
    currentLectureProgress = 0;
    audioStartTime = null;

    document.getElementById('lecture-status-text').textContent = '等待开始授课...';

    
    const supplementCard = document.getElementById('supplement-card');
    if (supplementCard) {
        supplementCard.classList.add('hidden');
    }

        const displayContainer = document.getElementById('teacher-lecture-display-container');
    if (displayContainer) {
        displayContainer.classList.add('hidden');
    }

    showToast('Lecture ended', 'success');
}

function stopTeacherLecturePlayback() {
    if (teacherPlaybackState.currentUtterance) {
        speechSynthesis.cancel();
        teacherPlaybackState.currentUtterance = null;
    }

    teacherPlaybackState.isPlaying = false;
    teacherPlaybackState.isPaused = false;

    document.getElementById('btn-teacher-play').disabled = true;
    document.getElementById('btn-teacher-pause').disabled = true;
    document.getElementById('btn-teacher-play').textContent = '播放';

    clearTeacherHighlights();
}

function showSupplementCard() {
    document.getElementById('supplement-card').classList.remove('hidden');
    document.getElementById('supplement-content').focus();
    showToast('Please enter supplement content', 'warning');

    // 涓嶅啀鑷姩鐢熸垚鏂囨湰
    // 绉婚櫎涔嬪墠鐨勮闊宠瘑鍒ā鎷?
}

function cancelSupplement() {
    isRecording = false;
    document.getElementById('supplement-card').classList.add('hidden');
    document.getElementById('supplement-content').value = '';
}

// ==================== 鐭ヨ瘑鍥捐氨鍔熻兘 ====================

async function updateKnowledgeGraph() {
    if (!EMBEDDED_GRAPH_ENABLED) {
        updateGraphPanelSummary();
        return;
    }

    try {
        showToast('正在从后端新版图谱加载知识图谱...', 'info');

        const response = await callMaintenanceAPI('/graph', 'GET');

        if (response.success && response.data) {
            const mcpData = response.data;

            graphData = {
                nodes: (mcpData.nodes || []).map(node => ({
                    id: node.id,
                    label: node.metadata?.label || node.label || (node.content ? node.content.substring(0, 30) + '...' : node.id),
                    type: node.type || 'concept',
                    content: node.content || '',
                    description: node.metadata?.description || node.content || '',
                    chapter: node.metadata?.chapter || '',
                    source: node.metadata?.source || '',
                    metadata: node.metadata || {}
                })),
                edges: (mcpData.relations || []).map(relation => ({
                    id: relation.id,
                    source: relation.source_id,
                    target: relation.target_id,
                    type: relation.relation_type || 'related',
                    label: relation.relation_type || 'related',
                    title: relation.metadata?.description || relation.relation_type || 'related',
                    metadata: relation.metadata || {}
                }))
            };

            console.log('已从 vector_index_system 后端图谱加载数据', {
                nodes: graphData.nodes.length,
                edges: graphData.edges.length
            });
            renderKnowledgeGraph();

            showToast(`知识图谱已更新：${graphData.nodes.length} 个节点，${graphData.edges.length} 条关系`, 'success');
        } else {
            throw new Error('获取后端图谱数据失败');
        }
    } catch (error) {
        console.error('从后端维护 API 获取知识图谱失败:', error);
        showToast('后端新版图谱加载失败，请检查维护 API 是否已启动。', 'error');
        graphData = { nodes: [], edges: [] };
        renderKnowledgeGraph();
    }
}

function updateGraphPanelSummary() {
    const container = document.getElementById('graph-page-placeholder');
    if (container) {
        container.innerHTML = `
            <div style="display:grid;gap:10px;">
                <div style="font-weight:600;color:#1f2937;">知识图谱使用后端管理页</div>
                <div style="color:#6b7280;font-size:13px;line-height:1.6;">
                    教师端不再内嵌渲染整张图，避免页面卡顿。请在后端知识图谱管理页查看和编辑
                    vector_index_system 图谱。
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <button onclick="openBackendGraphAdmin()" class="btn btn-info">打开后端知识图谱</button>
                </div>
            </div>
        `;
    }
}

// ==================== 鐭ヨ瘑鍥捐氨鎬昏 ====================

function openGraphOverview() {
    const overviewFloat = document.getElementById('graph-overview-float');
    const overviewContent = document.getElementById('graph-overview-content');
    if (!overviewFloat || !overviewContent) return;

    const nodes = getOverviewNodes();
    const edges = getOverviewEdges();

    
    const typeCounts = {};
    const typeRelationCounts = {};
    nodes.forEach(n => {
        const t = n.type || n._type || 'unknown';
        typeCounts[t] = (typeCounts[t] || 0) + 1;
        if (!typeRelationCounts[t]) typeRelationCounts[t] = { in: 0, out: 0 };
    });
    edges.forEach(e => {
        const srcNode = nodes.find(n => n.id === e.from);
        const tgtNode = nodes.find(n => n.id === e.to);
        if (srcNode) {
            const t = srcNode.type || srcNode._type || 'unknown';
            typeRelationCounts[t].out = (typeRelationCounts[t].out || 0) + 1;
        }
        if (tgtNode) {
            const t = tgtNode.type || tgtNode._type || 'unknown';
            typeRelationCounts[t].in = (typeRelationCounts[t].in || 0) + 1;
        }
    });

    const colorMap = {
        proposition: '#e74c3c', derivation: '#3498db', discussion: '#1abc9c',
        chapter: '#f39c12', formula: '#2ecc71', definition: '#9b59b6',
        concept: '#10b981', note: '#f59e0b', observation: '#3b82f6'
    };

    let html = '<div style="margin-bottom:16px;">';
    html += '<div style="font-weight:600;font-size:14px;margin-bottom:8px;">节点类型统计</div>';
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
    html += '<tr style="background:#f0f0f0;"><th style="padding:6px 10px;text-align:left;">类型</th><th style="padding:6px 10px;">数量</th><th style="padding:6px 10px;">入边</th><th style="padding:6px 10px;">出边</th></tr>';
    for (const [type, count] of Object.entries(typeCounts)) {
        const rel = typeRelationCounts[type] || { in: 0, out: 0 };
        const c = colorMap[type] || '#95a5a6';
        html += `<tr style="border-bottom:1px solid #eee;">
            <td style="padding:6px 10px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${c};margin-right:6px;"></span>${type}</td>
            <td style="padding:6px 10px;text-align:center;">${count}</td>
            <td style="padding:6px 10px;text-align:center;">${rel.in}</td>
            <td style="padding:6px 10px;text-align:center;">${rel.out}</td></tr>`;
    }
    html += '</table>';
    html += `<div style="margin-top:8px;font-size:12px;color:#888;">共 ${nodes.length} 个节点，${edges.length} 条关系</div>`;
    html += '</div>';

    
    const edgeTypeCounts = {};
    edges.forEach(e => {
        const t = e.label || e.type || 'unknown';
        edgeTypeCounts[t] = (edgeTypeCounts[t] || 0) + 1;
    });
    if (Object.keys(edgeTypeCounts).length > 0) {
        html += '<div style="margin-bottom:16px;">';
        html += '<div style="font-weight:600;font-size:14px;margin-bottom:8px;">关系类型统计</div>';
        html += '<div style="display:flex;flex-wrap:wrap;gap:6px;">';
        for (const [type, count] of Object.entries(edgeTypeCounts)) {
            html += `<span style="background:#e8f4f8;padding:4px 10px;border-radius:12px;font-size:12px;">${type}: ${count}</span>`;
        }
        html += '</div></div>';
    }

    // 3. Search and locate
    html += '<div style="border-top:1px solid #eee;padding-top:12px;">';
    html += '<div style="font-weight:600;font-size:14px;margin-bottom:8px;">搜索节点并定位</div>';
    html += '<div style="display:flex;gap:8px;margin-bottom:10px;">';
    html += '<input type="text" id="overview-search-input" placeholder="输入节点名称搜索..." style="flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;">';
    html += '<button onclick="searchOverviewNodes()" style="padding:8px 16px;background:#3498db;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">搜索</button>';
    html += '</div>';
    html += '<div id="overview-search-results" style="max-height:200px;overflow-y:auto;"></div>';
    html += '</div>';

    overviewContent.innerHTML = html;
    overviewFloat.classList.remove('hidden');

    // Make draggable
    makeDraggable(overviewFloat, document.getElementById('overview-drag-handle'));

    // Auto-search on typing
    setTimeout(() => {
        const input = document.getElementById('overview-search-input');
        if (input) {
            input.addEventListener('input', () => searchOverviewNodes());
            input.focus();
        }
    }, 100);
}

function closeGraphOverview() {
    const overviewFloat = document.getElementById('graph-overview-float');
    if (overviewFloat) overviewFloat.classList.add('hidden');
}

function getOverviewNodes() {
    if (visNetworkInstance) {
        return visNetworkInstance.body.data.nodes.get();
    }
    return graphData.nodes || [];
}

function getOverviewEdges() {
    if (visNetworkInstance) {
        return visNetworkInstance.body.data.edges.get();
    }
    return graphData.edges || [];
}

function searchOverviewNodes() {
    const input = document.getElementById('overview-search-input');
    const resultsDiv = document.getElementById('overview-search-results');
    if (!input || !resultsDiv) return;

    const term = input.value.toLowerCase().trim();
    const nodes = getOverviewNodes();

    if (!term) {
        resultsDiv.innerHTML = '';
        return;
    }

    const matches = nodes.filter(n => {
        const label = (n.label || n._full_label || n.id || '').toLowerCase();
        const content = (n._content || n.content || '').toLowerCase();
        return label.includes(term) || content.includes(term);
    }).slice(0, 20);

    if (matches.length === 0) {
        resultsDiv.innerHTML = '<div style="color:#999;padding:8px;font-size:13px;">未找到匹配节点</div>';
        return;
    }

    resultsDiv.innerHTML = matches.map(n => {
        const label = renderLatexContent(n._full_label || n.label || n.id);
        const plainLabel = cleanLatex(n._full_label || n.label || n.id);
        const shortLabel = plainLabel.length > 50 ? plainLabel.substring(0, 50) + '...' : plainLabel;
        const type = n._type || n.type || '';
        return `<div onclick="focusOnNode('${n.id}')" style="padding:8px 10px;border-bottom:1px solid #f0f0f0;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:8px;" onmouseover="this.style.background='#f0f7ff'" onmouseout="this.style.background=''">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${n.color?.background || '#95a5a6'};"></span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(plainLabel)}">${label}</span>
            <span style="color:#999;font-size:11px;">${type}</span>
        </div>`;
    }).join('');
}

function focusOnNode(nodeId) {
        if (visNetworkInstance) {
        // Ensure the interactive graph is visible first.
        if (!visGraphVisible) toggleVisGraph();

        visNetworkInstance.focus(nodeId, { scale: 1.5, animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
        visNetworkInstance.selectNodes([nodeId]);

        
        const nodeData = visNetworkInstance.body.data.nodes.get(nodeId);
        if (nodeData) showVisNodeDetail(nodeData);
    } else {
        // Fallback for the original graph: highlight via search.
        const searchInput = document.getElementById('graph-search-input');
        if (searchInput) {
            const node = (graphData.nodes || []).find(n => n.id === nodeId);
            searchInput.value = node ? (node.label || node.id) : nodeId;
            searchGraphNodes({ target: searchInput });
        }
    }
}

async function refreshGraph() {
    openBackendGraphAdmin();
}

function toggleFullScreen() {
    openBackendGraphAdmin();
}

// ESC to exit fullscreen
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const panel = document.querySelector('.graph-panel');
        if (panel && panel.classList.contains('graph-fullscreen')) {
            panel.classList.remove('graph-fullscreen');
            const container = document.getElementById('vis-graph-container');
            if (container) container.style.height = '600px';
            if (visNetworkInstance) visNetworkInstance.redraw();
        }
    }
});


// ==================== 鍥捐氨瀵煎嚭鍔熻兘 ====================

async function exportGraph() {
    try {
        const result = await callMaintenanceAPI('/export-graph', 'GET');

        if (result.success && result.data) {
            
            const dataStr = JSON.stringify(result.data, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(dataBlob);

            const link = document.createElement('a');
            link.href = url;
            link.download = `knowledge-graph-${new Date().toISOString().slice(0, 10)}.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            showToast('图谱导出成功', 'success');
        } else {
            throw new Error('瀵煎嚭澶辫触');
        }
    } catch (error) {
        console.error('瀵煎嚭鍥捐氨澶辫触:', error);
        showToast('导出失败，请稍后重试', 'error');
    }
}

async function scanStructuredData() {
    try {
        showToast('正在扫描 structured 并执行增量同步...', 'info');
        const result = await callMaintenanceAPI('/scan-structured', 'POST', { force: false });
        if (result.success) {
            const data = result.data || {};
            updateGraphPanelSummary();
            showToast(
                `同步完成：新增源 ${data.created_sources || 0}，更新源 ${data.updated_sources || 0}，章节 ${data.chapter_count || 0}`,
                'success'
            );
        }
    } catch (error) {
        console.error('structured 同步失败:', error);
        showToast('structured 同步失败', 'error');
    }
}

async function downloadTeacherPackage() {
    try {
        showToast('正在生成教师端可加载包...', 'info');
        const result = await callMaintenanceAPI('/export-teacher-package', 'GET');
        if (!result.success || !result.data) {
            throw new Error('Teacher package generation failed');
        }
        const dataStr = JSON.stringify(result.data, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'teacher_memory_package.json';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showToast('教师包已导出，可直接在教师端导入 JSON', 'success');
    } catch (error) {
        console.error('瀵煎嚭鏁欏笀鍖呭け璐?', error);
        showToast('Failed to export teacher package', 'error');
    }
}

function openReviewSearch() {
    const panel = document.getElementById('review-search-float');
    if (!panel) return;
    panel.classList.remove('hidden');
    makeDraggable(panel, document.getElementById('review-search-drag-handle'));
    const input = document.getElementById('review-search-input');
    if (input) input.focus();
}

function closeReviewSearch() {
    const panel = document.getElementById('review-search-float');
    if (panel) panel.classList.add('hidden');
}

async function runReviewSearch() {
    const input = document.getElementById('review-search-input');
    const chapterSelect = document.getElementById('review-search-chapter');
    const resultsEl = document.getElementById('review-search-results');
    if (!input || !resultsEl) return;

    const query = input.value.trim();
    if (!query) {
        showToast('Please enter search text', 'warning');
        return;
    }

    resultsEl.innerHTML = '<p class="loading">正在检索...</p>';
    try {
        const result = await callMaintenanceAPI('/review-search', 'POST', {
            query: query,
            limit: 10,
            chapter: chapterSelect ? chapterSelect.value : ''
        });
        const items = (result && result.results) || [];
        if (!items.length) {
            resultsEl.innerHTML = '<p class="placeholder">未找到相关节点</p>';
            return;
        }

        let html = '';
        items.forEach(function(item) {
            const node = item.node || {};
            const related = item.related || [];
            const chapter = (node.metadata && node.metadata.chapter) || '';
            html += `<div style="border:1px solid #eee;border-radius:8px;padding:12px;margin-bottom:10px;background:#fff;">`;
            html += `<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;">`;
            html += `<div>`;
            html += `<div style="font-weight:600;margin-bottom:4px;">${escapeHtml((node.metadata && node.metadata.label) || node.label || node.id || '')}</div>`;
            html += `<div style="font-size:12px;color:#666;">${escapeHtml(node.type || '')}${chapter ? ' 路 ' + escapeHtml(chapter) : ''}</div>`;
            html += `</div>`;
            html += `<button class="btn btn-small" onclick="locateGraphNode('${escapeHtml(node.id)}')">瀹氫綅</button>`;
            html += `</div>`;
            html += `<div style="margin-top:8px;font-size:12px;line-height:1.6;color:#444;">${escapeHtml((node.content || '').substring(0, 220))}</div>`;
            if (related.length) {
                html += `<div style="margin-top:10px;padding-top:8px;border-top:1px dashed #eee;">`;
                html += `<div style="font-weight:600;font-size:12px;margin-bottom:6px;">鐩稿叧杈?/div>`;
                related.forEach(function(relItem) {
                    const relation = relItem.relation || {};
                    const otherNode = relItem.other_node || {};
                    const relationType = relation.relation_type || relation.type || 'related';
                    html += `<div style="display:flex;justify-content:space-between;gap:8px;font-size:12px;padding:4px 0;">`;
                    html += `<div>${escapeHtml(relationType)} 鈫?${escapeHtml((otherNode.metadata && otherNode.metadata.label) || otherNode.label || otherNode.id || '')}</div>`;
                    html += `<button class="btn btn-small" onclick="openRelationEditorById('${escapeHtml(relation.id)}')">淇敼鍏崇郴</button>`;
                    html += `</div>`;
                });
                html += `</div>`;
            }
            html += `</div>`;
        });
        resultsEl.innerHTML = html;
    } catch (error) {
        console.error('瀹￠槄妫€绱㈠け璐?', error);
        resultsEl.innerHTML = '<p class="placeholder">检索失败</p>';
    }
}

function locateGraphNode(nodeId) {
    if (visNetworkInstance) {
        visNetworkInstance.focus(nodeId, { scale: 1.35, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
        visNetworkInstance.selectNodes([nodeId]);
        const nodeData = visNetworkInstance.body.data.nodes.get(nodeId);
        if (nodeData) loadNodeEditor(nodeId, nodeData);
    }
}

function openRelationEditorById(relationId) {
    if (!visNetworkInstance) return;
    let edgeData = visNetworkInstance.body.data.edges.get(relationId);
    if (!edgeData) {
        const normalized = normalizeGraphDataForVis(graphData);
        const fallback = normalized.edges.find(function(edge) { return edge.id === relationId; });
        if (fallback) {
            edgeData = {
                id: fallback.id,
                from: fallback.from,
                to: fallback.to,
                label: formatEdgeLabel(fallback.label || fallback.relationType || 'related'),
                _relation_id: fallback.id,
                _type: fallback.relationType || fallback.label || 'related',
                _description: fallback.description || '',
                _chapter: fallback.chapter || '',
                _similarity: fallback.similarity || ''
            };
        }
    }
    if (edgeData) {
        loadEdgeEditor(relationId, edgeData);
    }
}

// ==================== 鑺傜偣璇︽儏澧炲己 ====================

function closeNodeDetail() {
    const detailDiv = document.getElementById('node-detail');
    if (detailDiv) {
        detailDiv.classList.add('hidden');
    }
    currentNodeEditorState = null;
    currentEdgeEditorState = null;
}

// ==================== 闂瓟鍔熻兘 ====================


const DEEPSEEK_API_KEY = '';

let answerQueue = [];
let isProcessingAnswer = false;

async function askQuestion() {
    const question = document.getElementById('question-input').value;

    if (!question) {
        showToast('Please enter a question', 'warning');
        return;
    }

    

    try {
        
        const answer = await askQuestionWithAPI(question);

        // 鏄剧ず绛旀
        displayAnswer(answer);

        addToQaHistory(question, answer);

        // 娓呯┖杈撳叆
        document.getElementById('question-input').value = '';

        showToast('Question submitted', 'success');
    } catch (error) {
        console.error('鐢熸垚绛旀鍑洪敊:', error);
        
        const fallbackAnswer = generateKnowledgeBasedAnswer(question);
        displayAnswer(fallbackAnswer);
        addToQaHistory(question, fallbackAnswer);
        showToast('Answered using graph fallback', 'info');
    }
}

function buildKnowledgeGraphContext(question) {
    
    let context = `銆愮煡璇嗗浘璋变俊鎭€慭n\n`;

    
    if (currentChapter) {
        context += `褰撳墠绔犺妭锛?{currentChapter.title}\n`;
        context += `绔犺妭鍐呭锛?{currentChapter.content.substring(0, 200)}...\n\n`;
    }

    
    if (graphData.nodes && graphData.nodes.length > 0) {
        context += `鐩稿叧鐭ヨ瘑鑺傜偣锛歕n`;
        graphData.nodes.forEach((node, index) => {
            if (index < 5) { // 闄愬埗鏄剧ず鍓?涓妭鐐癸紝閬垮厤涓婁笅鏂囪繃闀?                context += `- ${node.label}锛堢被鍨嬶細${node.type}锛塡n`;
            }
        });
    }

    
    const lectureNote = document.getElementById('lecture-note').value;
    if (lectureNote && lectureNote.length > 50) {
        context += `\n銆愬綋鍓嶆巿璇惧唴瀹广€慭n${lectureNote.substring(0, 300)}...\n\n`;
    }

    return context;
}

async function generateAIAnswer(question, context) {
    
    if (!DEEPSEEK_API_KEY) {
                return await generateKnowledgeBasedAnswer(question);
    }

    try {
        const response = await fetch(DEEPSEEK_API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${DEEPSEEK_API_KEY}`
            },
            body: JSON.stringify({
                model: 'deepseek-v4flash',
                max_tokens: 1024,
                messages: [
                    {
                        role: 'system',
                        content: `你是一个专业的教育助手，请基于提供的知识图谱信息准确回答问题。`
                    },
                    {
                        role: 'user',
                        content: `${context}\n\n【问题】\n${question}\n\n请基于以上信息回答问题，如果信息不足请明确说明。`
                    }
                ]
            })
        });

        if (!response.ok) {
            throw new Error('API璇锋眰澶辫触');
        }

        const data = await response.json();
        return (((data || {}).choices || [])[0] || {}).message?.content || '';
    } catch (error) {
        console.error('DeepSeek API璋冪敤澶辫触:', error);
        throw error;
    }
}

function generateKnowledgeBasedAnswer(question) {
    
    let answer = `鍩轰簬褰撳墠鐭ヨ瘑鍥捐氨锛屽"${question}"鐨勫洖绛旓細\n\n`;

        const keywords = extractKeywords(question);

    
    const relatedNodes = graphData.nodes.filter(node =>
        keywords.some(keyword =>
            node.label.toLowerCase().includes(keyword.toLowerCase())
        )
    );

    if (relatedNodes.length === 0) {
        // 娌℃湁鎵惧埌鐩稿叧鑺傜偣
        answer += `鎶辨瓑锛屽綋鍓嶇煡璇嗗浘璋变腑鏆傛椂娌℃湁鎵惧埌涓庤闂鐩存帴鐩稿叧鐨勫唴瀹广€俓n\n`;
        answer += `寤鸿锛歕n`;
        answer += `1. 鍙互灏濊瘯浣跨敤涓嶅悓鐨勬彁闂柟寮廫n`;
        answer += `2. 绛夊緟鏁欏笀琛ュ厖鐩稿叧鐭ヨ瘑鍚庡啀鎻愰棶`;
        return answer;
    }

    // 鏋勫缓鍩轰簬鐩稿叧鑺傜偣鐨勭瓟妗?    answer += `鏍规嵁鐭ヨ瘑鍥捐氨锛屾壘鍒颁互涓嬬浉鍏崇煡璇嗙偣锛歕n\n`;

    relatedNodes.forEach((node, index) => {
        answer += `${index + 1}. ${node.label}\n`;
        answer += `   绫诲瀷锛?{node.type}\n`;
    });

        if (currentChapter) {
        answer += `\n杩欎簺鍐呭灞炰簬"${currentChapter.title}"杩欎竴绔犮€俓n\n`;
    }

    // 娣诲姞杩涗竴姝ュ缓璁?    answer += `娣卞叆鐞嗚В寤鸿锛歕n`;
    answer += `- 寤鸿缁撳悎璇惧爞璁茶В鍐呭杩涜瀛︿範\n`;
    answer += `- 鍙互鍏虫敞绔犺妭闂寸殑閫昏緫鍏崇郴\n`;

    return answer;
}

function extractKeywords(text) {
    
    const stopWords = ['的', '了', '是', '在', '和', '与', '我', '什么', '怎么', '如何', '为什么', '关于', '请问'];
    return text.split(/[锛屻€傦紵锛燂紒\s]+/)
        .map(word => word.trim())
        .filter(word => word.length > 0 && !stopWords.includes(word));
}

function generateMockAnswer(question) {
    
    return generateKnowledgeBasedAnswer(question);
}

function displayAnswer(answer) {
    const answerDiv = document.getElementById('answer-display');

        const formattedAnswer = formatAnswer(answer);
    answerDiv.innerHTML = formattedAnswer;
    answerDiv.classList.remove('hidden');
}

function formatAnswer(answer) {
    
    const paragraphs = answer.split('\n\n');
    return paragraphs.map(p => {
        if (p.trim().length === 0) return '';
        return `<div class="answer-content">${p.trim()}</div>`;
    }).join('');
}

function displayAnswer(answer) {
    const answerDiv = document.getElementById('answer-display');
    answerDiv.innerHTML = `
        <div class="answer-content">
            <p>${answer}</p>
        </div>
    `;
    answerDiv.classList.remove('hidden');
}

function addToQaHistory(question, answer) {
    qaHistory.unshift({ question, answer, time: new Date().toLocaleString() });

    const historyList = document.getElementById('history-list');
    let html = '';

    qaHistory.forEach((item, index) => {
        html += `
            <div class="history-item" onclick="showHistoryItem(${index})">
                <div class="history-question">Q: ${item.question}</div>
                <div class="history-answer">A: ${item.answer.substring(0, 50)}...</div>
                <div class="history-time" style="font-size: 11px; color: #999;">${item.time}</div>
            </div>
        `;
    });

    historyList.innerHTML = html;
}

function showHistoryItem(index) {
    const item = qaHistory[index];
    document.getElementById('question-input').value = item.question;
    displayAnswer(item.answer);
}

// ==================== 宸ュ叿鍑芥暟 ====================

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');

    toastMessage.textContent = message;

    
    const colors = {
        'success': '#10b981',
        'error': '#ef4444',
        'warning': '#f59e0b',
        'info': '#3b82f6'
    };
    toast.style.background = colors[type] || colors['info'];

    toast.classList.remove('hidden');
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 300);
    }, 3000);
}

function loadInitialData() {
    // 鍒濆鍖栫ず渚嬫暟鎹?    qaHistory = [];
    loadSavedChapterList();
    loadLectureChapterList();
}

// ==================== 浜嬩欢鐩戝惉 ====================

document.addEventListener('DOMContentLoaded', function() {
        const saveRecordBtn = document.getElementById('btn-save-lecture-record');
    if (saveRecordBtn) {
        saveRecordBtn.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            showContextMenu(e.clientX, e.clientY);
        });
    }

    // 鐐瑰嚮鍏朵粬鍦版柟鍏抽棴鍙抽敭鑿滃崟
    document.addEventListener('click', function() {
        if (isContextMenuShown) {
            hideContextMenu();
        }
    });

    // 鍒濆鍖栨嫋鎷藉姛鑳?    initDragFunctionality();
    initResizeFunctionality();

    // 鍔犺浇宸蹭繚瀛樼珷鑺傚垪琛?    loadSavedChapterList();
    loadLectureChapterList();

        const questionInput = document.getElementById('question-input');
    if (questionInput) {
        questionInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                askQuestion();
            }
        });
    }

    const reviewSearchInput = document.getElementById('review-search-input');
    if (reviewSearchInput) {
        reviewSearchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                runReviewSearch();
            }
        });
    }

    
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                login();
            }
        });
    }

});

// ==================== 鍙抽敭鑿滃崟鍔熻兘 ====================

function showContextMenu(x, y) {
    const menu = document.getElementById('context-menu');
    
    const menuWidth = 150;
    const menuHeight = 40;
    const maxX = window.innerWidth - menuWidth - 10;
    const maxY = window.innerHeight - menuHeight - 10;

    menu.style.left = Math.min(x, maxX) + 'px';
    menu.style.top = Math.min(y, maxY) + 'px';
    menu.classList.remove('hidden');
    isContextMenuShown = true;
}

function hideContextMenu() {
    const menu = document.getElementById('context-menu');
    menu.classList.add('hidden');
    isContextMenuShown = false;
}

// ==================== 鎷栨嫿鍔熻兘 ====================

function initDragFunctionality() {
    const qaWindow = document.getElementById('qa-float-window');
    const lectureFloat = document.getElementById('lecture-float-window');
    const voiceWindow = document.getElementById('voice-record-window');

    if (qaWindow) makeDraggable(qaWindow, document.getElementById('qa-float-header'));
    if (lectureFloat) makeDraggable(lectureFloat, document.querySelector('.lecture-float-header'));
    if (voiceWindow) makeDraggable(voiceWindow, document.querySelector('.voice-record-header'));

    
    const nodeDetail = document.getElementById('node-detail');
    const statsFloat = document.getElementById('graph-statistics-float');
    if (nodeDetail) makeDraggable(nodeDetail, nodeDetail.querySelector('.node-detail-header'));
    if (statsFloat) makeDraggable(statsFloat, statsFloat.querySelector('.statistics-header'));
}

function makeDraggable(element, handle) {
    if (!element || !handle) return;

    let isDragging = false;
    let startX, startY, initialX, initialY;

    handle.addEventListener('mousedown', startDrag);
    handle.addEventListener('touchstart', startDrag);

    function startDrag(e) {
        e.preventDefault();
        isDragging = true;

        const event = e.type === 'touchstart' ? e.touches[0] : e;
        startX = event.clientX;
        startY = event.clientY;

        const rect = element.getBoundingClientRect();
        initialX = rect.left;
        initialY = rect.top;

        document.addEventListener('mousemove', drag);
        document.addEventListener('touchmove', drag);
        document.addEventListener('mouseup', stopDrag);
        document.addEventListener('touchend', stopDrag);
    }

    function drag(e) {
        if (!isDragging) return;

        const event = e.type === 'touchmove' ? e.touches[0] : e;
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;

        element.style.left = `${initialX + deltaX}px`;
        element.style.top = `${initialY + deltaY}px`;
        element.style.right = 'auto';
        element.style.bottom = 'auto';
    }

    function stopDrag() {
        isDragging = false;
        document.removeEventListener('mousemove', drag);
        document.removeEventListener('touchmove', drag);
        document.removeEventListener('mouseup', stopDrag);
        document.removeEventListener('touchend', stopDrag);
    }
}

// ==================== 妯悜缂╂斁鍔熻兘 ====================

function initResizeFunctionality() {
    const editorWrapper = document.getElementById('lecture-editor-wrapper');
    if (editorWrapper) {
        const textarea = editorWrapper.querySelector('textarea');
        if (textarea) {
            
            const resizeHandle = document.createElement('div');
            resizeHandle.className = 'resize-handle';
            editorWrapper.appendChild(resizeHandle);

            let isResizing = false;
            let startX, startWidth;

            resizeHandle.addEventListener('mousedown', startResize);
            resizeHandle.addEventListener('touchstart', startResize);

            function startResize(e) {
                e.preventDefault();
                isResizing = true;
                startX = e.type === 'touchstart' ? e.touches[0].clientX : e.clientX;
                startWidth = editorWrapper.offsetWidth;

                document.addEventListener('mousemove', resize);
                document.addEventListener('touchmove', resize);
                document.addEventListener('mouseup', stopResize);
                document.addEventListener('touchend', stopResize);
            }

            function resize(e) {
                if (!isResizing) return;

                const eventX = e.type === 'touchmove' ? e.touches[0].clientX : e.clientX;
                const deltaX = eventX - startX;
                const newWidth = Math.max(200, startWidth + deltaX);
                const maxWidth = window.innerWidth - 40;

                editorWrapper.style.width = `${Math.min(newWidth, maxWidth)}px`;
                textarea.style.width = '100%';
            }

            function stopResize() {
                isResizing = false;
                document.removeEventListener('mousemove', resize);
                document.removeEventListener('touchmove', resize);
                document.removeEventListener('mouseup', stopResize);
                document.removeEventListener('touchend', stopResize);
            }
        }
    }
}

// ==================== 鏁欏笀绔巿璇惧睍绀哄姛鑳?====================

function showTeacherLectureDisplay() {
    const displayContainer = document.getElementById('teacher-lecture-display-container');
    if (displayContainer) {
        displayContainer.classList.remove('hidden');
    }

    refreshTeacherGraph();
}

function loadTeacherLectureContent(content) {
    teacherPlaybackState.fullContent = content;
    teacherPlaybackState.currentPosition = 0;

    parseTeacherKnowledgePoints(content);

    // 鍚敤鎾斁鎸夐挳
    document.getElementById('btn-teacher-play').disabled = false;

    // 鍒濆鏄剧ず
    updateTeacherLectureDisplay(0);

    // 灏嗘寜閽枃鏈噸缃负"鎾斁"
    document.getElementById('btn-teacher-play').textContent = '播放';
}

// 瑙ｆ瀽鏁欏笀绔枃妗堜腑鐨勭煡璇嗙偣
function parseTeacherKnowledgePoints(content) {
    teacherKnowledgePoints = [];

    // 鑾峰彇鐭ヨ瘑鍥捐氨鏁版嵁
    fetchTeacherGraphData().then(data => {
        if (data && data.nodes) {
            // 涓烘瘡涓妭鐐瑰湪鍐呭涓煡鎵惧嚭鐜扮殑浣嶇疆
            data.nodes.forEach(node => {
                const positions = findTeacherKeywordPositions(content, node.label);
                if (positions.length > 0) {
                    teacherKnowledgePoints.push({
                        keyword: node.label,
                        nodeId: node.id,
                        positions: positions,
                        type: node.type
                    });
                }
            });

            teacherKnowledgePoints.sort((a, b) => a.positions[0] - b.positions[0]);
        }
    });
}

// 鏌ユ壘鍏抽敭璇嶅湪鍐呭涓殑鎵€鏈変綅缃紙鏁欏笀绔級
function findTeacherKeywordPositions(content, keyword) {
    const positions = [];
    let index = content.indexOf(keyword);
    while (index !== -1) {
        positions.push(index);
        index = content.indexOf(keyword, index + 1);
    }
    return positions;
}

async function fetchTeacherGraphData() {
    return null;
}

function playTeacherLecture() {
    const content = teacherPlaybackState.fullContent;

    if (!content) {
        showToast('没有可播放的内容');
        return;
    }

    if (!window.speechSynthesis) {
        showToast('你的浏览器不支持语音播放功能', 'error');
        return;
    }

    // 鍙栨秷涔嬪墠鐨勬挱鏀?    speechSynthesis.cancel();

    teacherPlaybackState.isPlaying = true;
    teacherPlaybackState.isPaused = false;
    teacherPlaybackState.currentPosition = 0;

    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // 鐩戝惉杈圭晫浜嬩欢锛堣幏鍙栨挱鏀句綅缃級
    utterance.onboundary = (event) => {
        if (event.name === 'word') {
            teacherPlaybackState.currentPosition = event.charIndex;
            updateTeacherLectureDisplay(event.charIndex);
            updateTeacherGraphHighlights(event.charIndex);
        }
    };

    // 鎾斁缁撴潫
    utterance.onend = () => {
        teacherPlaybackState.isPlaying = false;
        teacherPlaybackState.isPaused = false;
        document.getElementById('btn-teacher-play').disabled = false;
        document.getElementById('btn-teacher-pause').disabled = true;
        document.getElementById('btn-teacher-play').textContent = '播放';
        clearTeacherHighlights();
        showToast('播放完成', 'success');
    };

    // 鎾斁閿欒
    utterance.onerror = (error) => {
        console.error('语音播放错误:', error);
        teacherPlaybackState.isPlaying = false;
        document.getElementById('btn-teacher-play').disabled = false;
        document.getElementById('btn-teacher-pause').disabled = true;
        document.getElementById('btn-teacher-play').textContent = '播放';
        showToast('语音播放出错', 'error');
    };

    teacherPlaybackState.currentUtterance = utterance;
    speechSynthesis.speak(utterance);

    document.getElementById('btn-teacher-play').disabled = true;
    document.getElementById('btn-teacher-pause').disabled = false;
}

function pauseTeacherLecture() {
    if (!teacherPlaybackState.isPlaying) {
        return;
    }

    if (teacherPlaybackState.isPaused) {
        // 鎭㈠鎾斁
        teacherPlaybackState.isPaused = false;
        speechSynthesis.resume();
        document.getElementById('btn-teacher-pause').textContent = '暂停';
        document.getElementById('btn-teacher-play').textContent = '播放中...';
        showToast('继续播放', 'info');
    } else {
        // 鏆傚仠鎾斁
        teacherPlaybackState.isPaused = true;
        speechSynthesis.pause();
        document.getElementById('btn-teacher-pause').textContent = '继续';
        document.getElementById('btn-teacher-play').textContent = 'Paused';
        showToast('Playback paused', 'info');
    }
}

function updateTeacherLectureDisplay(currentPosition) {
    const displayDiv = document.getElementById('teacher-lecture-display-text');
    const content = teacherPlaybackState.fullContent;

    if (!content) return;

    if (teacherPlaybackState.showFullContent) {
        // 鏄剧ず鍏ㄩ儴鍐呭
        renderTeacherFullContentWithHighlights(content, currentPosition);
    } else {
        
        const range = 50;
        const startPos = Math.max(0, currentPosition - range);
        const endPos = Math.min(content.length, currentPosition + range);
        const displayText = content.substring(startPos, endPos);

        renderTeacherPartialContentWithHighlights(displayText, currentPosition, startPos);
    }
}

// 娓叉煋鏁欏笀绔叏閮ㄥ唴瀹癸紙甯﹂珮浜級
function renderTeacherFullContentWithHighlights(content, currentPosition) {
    const displayDiv = document.getElementById('teacher-lecture-display-text');

    let html = '';
    let lastIndex = 0;

    
    const sortedPoints = [...teacherKnowledgePoints].sort((a, b) => a.positions[0] - b.positions[0]);

    sortedPoints.forEach(point => {
        
        const relevantPosition = point.positions.find(pos => pos >= lastIndex);
        if (relevantPosition === undefined) return;

        html += escapeTeacherHtml(content.substring(lastIndex, relevantPosition));

                const isActive = currentPosition >= relevantPosition &&
                        currentPosition <= relevantPosition + point.keyword.length;

        
        const highlightClass = isActive ? 'knowledge-keyword active' : 'knowledge-keyword';
        html += `<span class="${highlightClass}" data-node-id="${point.nodeId}">
                  ${point.keyword}
                </span>`;

        lastIndex = relevantPosition + point.keyword.length;
    });

    
    if (lastIndex < content.length) {
        html += escapeTeacherHtml(content.substring(lastIndex));
    }

    displayDiv.innerHTML = html;
}

// 娓叉煋鏁欏笀绔儴鍒嗗唴瀹癸紙甯﹂珮浜級
function renderTeacherPartialContentWithHighlights(partialText, currentPosition, contentOffset) {
    const displayDiv = document.getElementById('teacher-lecture-display-text');

    
    const relativePosition = currentPosition - contentOffset;

    let html = '';
    let lastIndex = 0;

    teacherKnowledgePoints.forEach(point => {
        point.positions.forEach(pos => {
            
            if (pos >= contentOffset && pos + point.keyword.length <= contentOffset + partialText.length) {
                const relativePos = pos - contentOffset;

                html += escapeTeacherHtml(partialText.substring(lastIndex, relativePos));

                                const isActive = currentPosition >= pos &&
                                currentPosition <= pos + point.keyword.length;

                
                const highlightClass = isActive ? 'knowledge-keyword active' : 'knowledge-keyword';
                html += `<span class="${highlightClass}" data-node-id="${point.nodeId}">
                          ${point.keyword}
                        </span>`;

                lastIndex = relativePos + point.keyword.length;
            }
        });
    });

    
    if (lastIndex < partialText.length) {
        html += escapeTeacherHtml(partialText.substring(lastIndex));
    }

    displayDiv.innerHTML = html;
}

function updateTeacherGraphHighlights(currentPosition) {
    const activeNodeIds = new Set();

    teacherKnowledgePoints.forEach(point => {
        point.positions.forEach(pos => {
            if (currentPosition >= pos && currentPosition <= pos + point.keyword.length) {
                activeNodeIds.add(point.nodeId);
            }
        });
    });

    // 鏇存柊楂樹寒鏄剧ず
    highlightTeacherGraphNodes(activeNodeIds);
}

function highlightTeacherGraphNodes(activeNodeIds) {
    document.querySelectorAll('#teacher-knowledge-graph .node').forEach(node => {
        node.classList.remove('highlighted');
        node.style.transform = '';
    });

    // 楂樹寒娲昏穬鑺傜偣
    activeNodeIds.forEach(nodeId => {
        const nodeElement = document.getElementById(`teacher-node-${nodeId}`);
        if (nodeElement) {
            nodeElement.classList.add('highlighted');

            nodeElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    });
}

function clearTeacherHighlights() {
    // 娓呴櫎鏂囨楂樹寒
    document.querySelectorAll('#teacher-lecture-display-text .knowledge-keyword').forEach(kw => {
        kw.classList.remove('active');
    });

    // 娓呴櫎鍥捐氨楂樹寒
    document.querySelectorAll('#teacher-knowledge-graph .node').forEach(node => {
        node.classList.remove('highlighted');
        node.style.transform = '';
    });
}

// 鍒囨崲鏁欏笀绔樉绀哄叏閮?閮ㄥ垎鍐呭
function toggleTeacherFullContent() {
    const btn = document.getElementById('btn-teacher-show-full');
    const displayDiv = document.getElementById('teacher-lecture-display-text');

    if (teacherPlaybackState.showFullContent) {
        teacherPlaybackState.showFullContent = false;
        btn.textContent = '显示全部';
        displayDiv.classList.remove('show-full');
        displayDiv.classList.add('show-partial');
        updateTeacherLectureDisplay(teacherPlaybackState.currentPosition);
    } else {
        teacherPlaybackState.showFullContent = true;
        btn.textContent = '显示部分';
        displayDiv.classList.remove('show-partial');
        displayDiv.classList.add('show-full');
        renderTeacherFullContent();
    }
}

function renderTeacherFullContent() {
    const content = teacherPlaybackState.fullContent;
    renderTeacherFullContentWithHighlights(content, teacherPlaybackState.currentPosition);
}

function refreshTeacherGraph() {
    displayTeacherGraph(null);
}

function displayTeacherGraph(graphData) {
    const graphContainer = document.getElementById('teacher-knowledge-graph');

    if (graphContainer && graphData.nodes) {
        let html = '<div class="graph-nodes" style="display: flex; flex-wrap: wrap; gap: 10px; padding: 20px;">';
        graphData.nodes.forEach(node => {
            const color = getNodeColor(node.type);
            
            const convertedLabel = convertLatexToHtml(node.label);
            html += `<div class="node ${node.size}"
                     id="teacher-node-${node.id}"
                     style="background: ${color}; padding: 10px 15px; border-radius: 8px; cursor: pointer; transition: all 0.3s ease;"
                     onclick="showNodeDetail('${node.id}')"
                     title="${convertLatexToHtml(node.description || node.label)}">
                     ${convertedLabel}
                   </div>`;
        });
        html += '</div>';
        graphContainer.innerHTML = html;
    } else {
        graphContainer.innerHTML = `
            <div class="graph-placeholder">
                <p>知识图谱请在后端管理页查看，避免授课端卡顿。</p>
                <button onclick="openBackendGraphAdmin()" class="btn btn-small">打开后端知识图谱</button>
            </div>
        `;
    }
}

function escapeTeacherHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 璁剧疆鍔熻兘 ====================

// 鍒囨崲璁剧疆寮圭獥
function toggleSettingsWindow() {
    console.log('toggleSettingsWindow called');
    const settingsModal = document.getElementById('settings-modal');
    console.log('settingsModal:', settingsModal);
    if (settingsModal) {
        if (settingsModal.classList.contains('hidden')) {
            
            const savedApiKey = getStoredApiKey();
            document.getElementById('deepseek-api-key').value = savedApiKey || '';
            settingsModal.classList.remove('hidden');
            console.log('璁剧疆寮圭獥宸叉墦寮€');
        } else {
            closeSettingsModal();
            console.log('settings modal closed');
        }
    }
}

// 鍏抽棴璁剧疆寮圭獥
function closeSettingsModal() {
    const settingsModal = document.getElementById('settings-modal');
    if (settingsModal) {
        settingsModal.classList.add('hidden');
    }
}

// 淇濆瓨璁剧疆
function saveSettings() {
    const apiKey = document.getElementById('deepseek-api-key').value.trim();

    if (apiKey) {
        // 淇濆瓨鍒?localStorage
        localStorage.setItem('deepseek_api_key', apiKey);
        showToast('API 密钥已保存', 'success');
        closeSettingsModal();
    } else {
        // 娓呴櫎淇濆瓨鐨凙PI瀵嗛挜
        localStorage.removeItem('deepseek_api_key');
        localStorage.removeItem('claude_api_key');
        showToast('API 密钥已清除', 'info');
        closeSettingsModal();
    }
}

// 娴嬭瘯 API 瀵嗛挜
async function testApiKey() {
    const apiKey = document.getElementById('deepseek-api-key').value.trim();

    if (!apiKey) {
        showToast('请输入 API 密钥', 'warning');
        return;
    }

    showToast('正在测试 API 连接...', 'info');

    try {
        const response = await fetch(`${API_BASE_URL}/generate-lecture`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chapter_id: 'test',
                chapter_title: '测试',
                chapter_content: '测试内容',
                style: '测试',
                api_key: apiKey
            })
        });

        const result = await response.json();

        if (result.success) {
            showToast('API 测试成功', 'success');
        } else if (result.error && result.error.includes('API密钥')) {
            showToast('API 密钥无效，请检查后重试', 'error');
        } else {
            showToast('API 测试失败：' + (result.error || '未知错误'), 'error');
        }
    } catch (error) {
        console.error('API 测试失败:', error);
        showToast('API 测试失败，请检查连接', 'error');
    }
}

// 鍒囨崲 API 瀵嗛挜鏄剧ず/闅愯棌
function toggleApiKeyVisibility() {
    const apiKeyInput = document.getElementById('deepseek-api-key');
    if (apiKeyInput.type === 'password') {
        apiKeyInput.type = 'text';
    } else {
        apiKeyInput.type = 'password';
    }
}

// 鑾峰彇褰撳墠鐢ㄦ埛鐨?API 瀵嗛挜
function getStoredApiKey() {
    return localStorage.getItem('deepseek_api_key') || localStorage.getItem('claude_api_key') || '';
}

function getUserApiKey() {
    return getStoredApiKey();
}




