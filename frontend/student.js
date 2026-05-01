// 瀛︾敓绔疛avaScript鍔熻兘

console.log('学生端 JavaScript 加载完成');


let isLoggedIn = false;
let currentUser = null;
let userRole = 'student'; // 'student' or 'teacher'


let currentChapter = null;
let learningProgress = 0;
let learnedChapters = []; 
let totalChapters = [];


let currentExercise = null;
let exerciseBank = [];
let currentExerciseIndex = 0;
let exerciseProgress = 0;
let exerciseHistory = [];
let currentAnswer = null;
let currentExerciseChapterId = '';
let exerciseSelections = {};
let exerciseResults = {};


let qaHistory = [];


let playbackState = {
    isPlaying: false,
    isPaused: false,
    currentPosition: 0,      // 褰撳墠鎾斁鍒扮殑瀛楃浣嶇疆
    currentUtterance: null,  // 褰撳墠璇煶瀵硅薄
    fullContent: '',
    showFullContent: false,
    highlightedNodes: new Set(), // 褰撳墠楂樹寒鐨勮妭鐐笽D闆嗗悎
    lastRenderedLectureText: '',
    lastRenderedAt: 0,
    renderTimer: null
};


let graphData = null;
let knowledgePoints = []; // 鏂囨涓殑鐭ヨ瘑鐐规槧灏?
// ==================== API璋冪敤鍑芥暟 ====================

function renderRichText(text) {
    if (typeof window.renderMarkdown === 'function') {
        return window.renderMarkdown(text || '');
    }
    return escapeHtml(text || '').replace(/\n/g, '<br>');
}

function renderRichInline(text) {
    if (typeof window.renderMarkdownInline === 'function') {
        return window.renderMarkdownInline(text || '');
    }
    return escapeHtml(text || '');
}

function setRichContent(element, text, options) {
    if (!element) return;
    const settings = options || {};
    if (typeof window.setMarkdownContent === 'function') {
        window.setMarkdownContent(element, text || '', settings);
    } else {
        element.classList.add(settings.inline ? 'markdown-inline' : 'markdown-body');
        element.innerHTML = settings.inline ? renderRichInline(text || '') : renderRichText(text || '');
    }
    queueLatexRender(element);
}

function queueLatexRender(root) {
    if (typeof window.scheduleLatexRender === 'function') {
        window.scheduleLatexRender(root || document.body);
    } else if (typeof window.renderLatexIn === 'function') {
        window.renderLatexIn(root || document.body);
    }
}

function normalizeBaseUrl(value, fallback) {
    return (value || fallback).replace(/\/+$/, '');
}

const APP_CONFIG = window.__APP_CONFIG__ || {};
const EDUCATION_API_BASE_URL = normalizeBaseUrl(APP_CONFIG.educationApiBaseUrl, 'http://127.0.0.1:8001');
const MAINTENANCE_API_BASE_URL = normalizeBaseUrl(APP_CONFIG.maintenanceApiBaseUrl, 'http://127.0.0.1:8002');
const BACKEND_ADMIN_BASE_URL = normalizeBaseUrl(APP_CONFIG.backendAdminBaseUrl, 'http://127.0.0.1:8080');

function openBackendGraphAdmin() {
    window.open(`${BACKEND_ADMIN_BASE_URL}/admin`, '_blank', 'noopener');
}

async function callAPI(endpoint, method, data) {

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
        const longRunningRequest = String(endpoint || '').includes('/generate-exercises');
        let timeoutId = null;
        if (!longRunningRequest) {
            const controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), 60000);
            options.signal = controller.signal;
        }

        if (method !== 'GET' && data) {
            options.body = JSON.stringify(data);
        }

        
        let url = `${EDUCATION_API_BASE_URL}${endpoint}`;
        if (method === 'GET' && data) {
            const params = new URLSearchParams();
            for (const key in data) {
                params.append(key, data[key]);
            }
            url += '?' + params.toString();
        }

        try {
            const response = await fetch(url, options);
            const result = await response.json();
            return result;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
        }
    } catch (error) {
        console.error('API 调用失败:', error);

        // 鏄剧ずAPI杩炴帴澶辫触鎻愮ず
        showAPIConnectionError();

        return {
            success: false,
            error: error.message
        };
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
        const response = await fetch(`${EDUCATION_API_BASE_URL}/api/health`);
        if (response.ok) {
            showToast('API 已连接', 'success');
            // 閲嶆柊鍔犺浇褰撳墠鏁版嵁
            refreshGraph();
            loadChapterList();
        } else {
            throw new Error('API not responding');
        }
    } catch (error) {
        console.error('重新连接失败:', error);
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

// ==================== 鐧诲綍鍔熻兘 ====================

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!username || !password) {
        showToast('请输入学号和密码', 'warning');
        return;
    }

    
    const data = await callAPI('/api/student/login', 'POST', {
        username: username,
        password: password
    });

    if (data && data.success) {
        isLoggedIn = true;
        currentUser = data;
        showToast('登录成功', 'success');

        showPage('student-page');

        // 鏇存柊鐢ㄦ埛淇℃伅鏄剧ず
        document.getElementById('current-user').textContent = data.username || '学生';

        // 鍒锋柊鐭ヨ瘑鍥捐氨
        refreshGraph();
    } else {
        showToast(data.error || '登录失败', 'error');
        console.error('登录失败:', data);
    }
}

function switchRole(role) {
    userRole = role;

    
    if (role === 'teacher') {
        window.location.href = 'teacher.html';
        return;
    }

    
    const loginTitle = document.querySelector('#login-page h1');
    const loginSubtitle = document.querySelector('#login-page .subtitle');
    const roleSelector = document.querySelector('.role-selector');

    if (role === 'student') {
        loginTitle.textContent = '知识图谱教学系统';
        loginSubtitle.textContent = '学生登录';
        roleSelector.innerHTML = `
            <button onclick="switchRole('student')" class="role-btn active">学生登录</button>
            <button onclick="switchRole('teacher')" class="role-btn">教师登录</button>
        `;
    }
}

function logout() {
    isLoggedIn = false;
    currentUser = null;
    userRole = 'student';

    showPage('login-page');
    showToast('Logged out', 'info');
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
    const learnPanel = document.getElementById('learn-mode-panel');
    const practicePanel = document.getElementById('practice-mode-panel');

    learnPanel.classList.remove('active');
    practicePanel.classList.remove('active');

    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('active');
    });

        if (mode === 'learn') {
        learnPanel.classList.add('active');
        document.getElementById('btn-learn-mode').classList.add('active');
    } else if (mode === 'practice') {
        practicePanel.classList.add('active');
        document.getElementById('btn-practice-mode').classList.add('active');
        const selectedId = resolvePracticeChapterId();
        if (selectedId && selectedId !== currentExerciseChapterId) {
            loadExercises();
        }
    }

    showToast(`已切换到${mode === 'learn' ? '学习' : '练习'}模式`, 'info');
}

// ==================== 瀛︿範妯″紡 ====================

async function loadChapterList() {
    try {
        const data = await callAPI('/api/education/list-chapters', 'GET');
        if (data.success && Array.isArray(data.chapters) && data.chapters.length > 0) {
            updateChapterSelects(data.chapters);
            return;
        }
        throw new Error(data.error || data.detail || 'No chapters returned');
    } catch (error) {
        console.error('鍔犺浇绔犺妭鍒楄〃澶辫触:', error);
        const cachedChapters = await loadCachedChapterList();
        if (cachedChapters.length > 0) {
            updateChapterSelects(cachedChapters);
            showToast('已使用本地章节缓存', 'warning');
        }
    }
}

async function loadCachedChapterList() {
    try {
        const response = await fetch(`chapters-cache.json?ts=${Date.now()}`);
        if (!response.ok) {
            throw new Error('chapter cache not available');
        }
        const payload = await response.json();
        const chapters = payload && payload.chapters && typeof payload.chapters === 'object'
            ? Object.values(payload.chapters)
            : [];
        return normalizeChapterRecords(chapters);
    } catch (error) {
        console.warn('Chapter cache unavailable:', error);
        return [];
    }
}

function getChapterIdentity(chapter) {
    const id = String((chapter && chapter.id) || '').trim();
    const lowerId = id.toLowerCase();
    if (lowerId.startsWith('chapter::')) {
        return lowerId.slice('chapter::'.length);
    }
    if (lowerId.startsWith('chapter_')) {
        return lowerId.slice('chapter_'.length);
    }
    return lowerId || String((chapter && chapter.title) || '').trim().toLowerCase();
}

function textLength(value) {
    return typeof value === 'string' ? value.length : 0;
}

function chapterDetailScore(chapter) {
    return textLength(chapter.content) +
        textLength(chapter.lecture_content) * 2 +
        (chapter.graph_data ? 1000 : 0) +
        (String(chapter.id || '').startsWith('chapter::') ? 100 : 0);
}

function timestampValue(value) {
    if (typeof value === 'number') {
        return value > 1e12 ? value / 1000 : value;
    }
    const text = String(value || '').trim();
    if (!text) return 0;
    const numeric = Number(text);
    if (!Number.isNaN(numeric)) {
        return numeric > 1e12 ? numeric / 1000 : numeric;
    }
    const parsed = Date.parse(text);
    return Number.isNaN(parsed) ? 0 : parsed / 1000;
}

function normalizeChapterRecords(chapters) {
    const bestByIdentity = new Map();
    chapters.forEach(chapter => {
        if (!chapter || !chapter.id) return;
        const identity = getChapterIdentity(chapter);
        const current = bestByIdentity.get(identity);
        if (!current || chapterDetailScore(chapter) > chapterDetailScore(current)) {
            bestByIdentity.set(identity, chapter);
        }
    });
    return Array.from(bestByIdentity.values()).sort((a, b) => {
        return timestampValue(b.updated_at || b.created_at) - timestampValue(a.updated_at || a.created_at);
    });
}

function updateChapterSelects(chapters) {
    const learnSelect = document.getElementById('chapter-select');
    const practiceSelect = document.getElementById('practice-chapter-select');
    const normalizedChapters = normalizeChapterRecords(chapters);

    totalChapters = normalizedChapters.map(chapter => chapter.id);

    
    if (learnSelect) {
        const currentValue = learnSelect.value;
        learnSelect.innerHTML = '<option value="">-- 请选择章节 --</option>';
        normalizedChapters.forEach(chapter => {
            const option = document.createElement('option');
            option.value = chapter.id;
            option.textContent = chapter.title || chapter.id;
            learnSelect.appendChild(option);
        });
        if (currentValue) {
            learnSelect.value = currentValue;
        }
    }

    
    if (practiceSelect) {
        const currentValue = practiceSelect.value;
        practiceSelect.innerHTML = '<option value="">-- 请选择章节 --</option>';
        normalizedChapters.forEach(chapter => {
            const option = document.createElement('option');
            option.value = chapter.id;
            option.textContent = chapter.title || chapter.id;
            practiceSelect.appendChild(option);
        });
        if (currentValue) {
            practiceSelect.value = currentValue;
        }
    }
}

function onChapterChange() {
    const selectedId = document.getElementById('chapter-select').value;

    if (!selectedId) {
        showToast('请先选择学习章节', 'warning');
        return;
    }

    // 鑾峰彇绔犺妭鍐呭
    callAPI('/api/student/chapter', 'GET', { chapter_id: selectedId }).then(data => {
        if (data.success) {
            currentChapter = data;
            const practiceSelect = document.getElementById('practice-chapter-select');
            if (practiceSelect && selectedId) {
                practiceSelect.value = selectedId;
            }
            displayChapterContent(data.content);
            updateProgress(0);
            showToast(`已加载章节：${data.title}`, 'success');

            document.getElementById('btn-play-content').disabled = false;
            document.getElementById('btn-mark-learned').disabled = false;

            // 鍔犺浇瀛︿範璺緞鎺ㄨ崘
            loadLearningPath(selectedId);
        } else {
            showToast('加载章节失败', 'error');
        }
    }).catch(error => {
        console.error('加载章节失败:', error);
        showToast('加载章节失败，请稍后重试', 'error');
    });
}

// 鍔犺浇瀛︿範璺緞鎺ㄨ崘
async function loadLearningPath(chapterId) {
    try {
        const response = await fetch(`${EDUCATION_API_BASE_URL}/api/student/learning-path`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chapter_id: chapterId,
                learned_chapters: learnedChapters
            })
        });

        const result = await response.json();

        if (result.success && result.learning_path) {
            displayLearningPath(result.learning_path);
        }
    } catch (error) {
        console.error('鍔犺浇瀛︿範璺緞澶辫触:', error);
    }
}

// 鏄剧ず瀛︿範璺緞鎺ㄨ崘
function displayLearningPath(learningPath) {
    
    const graphPanel = document.querySelector('.knowledge-graph-panel');
    if (!graphPanel) return;

        let pathContainer = document.getElementById('learning-path-info');
    if (!pathContainer) {
        pathContainer = document.createElement('div');
        pathContainer.id = 'learning-path-info';
        pathContainer.className = 'learning-path-info';
        graphPanel.insertBefore(pathContainer, document.getElementById('knowledge-graph'));
    }

    let pathHtml = '<div class="learning-path-header">学习路径推荐</div>';

    
    const prereqs = learningPath.prerequisites;
    if (prereqs && prereqs.unlearned && prereqs.unlearned.length > 0) {
        pathHtml += '<div class="path-section">';
        pathHtml += '<div class="path-section-title">建议先学习：</div>';
        pathHtml += '<div class="path-items">';
        prereqs.unlearned.forEach(item => {
            const nodeName = item.node?.label || item.node_id;
            pathHtml += `<span class="path-item path-item-warning">${renderRichInline(nodeName)}</span>`;
        });
        pathHtml += '</div></div>';
    }

    // 褰撳墠绔犺妭
    pathHtml += '<div class="path-section">';
    pathHtml += '<div class="path-section-title">当前学习：</div>';
    pathHtml += `<div class="path-items"><span class="path-item path-item-current">${renderRichInline(currentChapter?.title || '当前章节')}</span></div>`;
    pathHtml += '</div>';

    
    const followUp = learningPath.follow_up;
    if (followUp && followUp.recommended && followUp.recommended.length > 0) {
        pathHtml += '<div class="path-section">';
        pathHtml += '<div class="path-section-title">推荐后续学习：</div>';
        pathHtml += '<div class="path-items">';
        followUp.recommended.forEach(item => {
            const nodeName = item.node?.label || item.node_id;
            pathHtml += `<span class="path-item path-item-recommend">${renderRichInline(nodeName)}</span>`;
        });
        pathHtml += '</div></div>';
    }

    pathContainer.innerHTML = pathHtml;
    queueLatexRender(pathContainer);
}

function displayChapterContent(content) {
    const courseContent = document.getElementById('course-content');
    const lectureFloat = document.getElementById('lecture-note-float');
    if (courseContent) {
        const text = String(content || '').trim() || '暂无课程内容';
        setRichContent(courseContent, text);
        courseContent.dataset.rawContent = text;
        if (lectureFloat) {
            setRichContent(lectureFloat, text);
            lectureFloat.dataset.rawContent = text;
        }
    }
}

function getCourseContentText() {
    const courseContent = document.getElementById('course-content');
    if (!courseContent) return '';
    return courseContent.dataset.rawContent || courseContent.textContent || '';
}

function updateProgress(progress) {
    learningProgress = progress;

    
    const totalProgress = document.getElementById('total-progress');
    const chapterProgress = document.getElementById('chapter-progress');

    if (totalProgress) {
        totalProgress.style.width = `${progress}%`;
    }

    if (chapterProgress) {
        chapterProgress.textContent = `学习进度：${progress}%`;
    }

    
    const progressBadges = document.getElementById('progress-badges');
    if (progressBadges) {
        const completedCount = Math.floor(progress / 25);         let badgesHtml = '';
        for (let i = 0; i < 4; i++) {
            if (i < completedCount) {
                badgesHtml += '<span class="badge completed">鈽?/span>';
            } else {
                badgesHtml += '<span class="badge">鈽?/span>';
            }
        }
        progressBadges.innerHTML = badgesHtml;
    }
}

function markAsLearned() {
    const selectedId = document.getElementById('chapter-select').value;

    if (!selectedId) {
        showToast('请先选择章节', 'warning');
        return;
    }

    callAPI('/api/student/mark-chapter', 'POST', {
        chapter_id: selectedId
    }).then(data => {
        if (data.success) {
            // 娣诲姞鍒板凡瀛︿範鍒楄〃
            learnedChapters.push(selectedId);
            updateProgress(learningProgress + (100 / Math.max(1, totalChapters.length)));

            showToast('Marked as learned', 'success');
        } else {
            showToast('标记失败', 'error');
        }
    });
}

function playContent() {
    const content = getCourseContentText().trim();

    if (!content) {
        showToast('没有可播放的内容', 'warning');
        return;
    }

    // 淇濆瓨瀹屾暣鍐呭
    playbackState.fullContent = content;
    playbackState.currentPosition = 0;
    playbackState.isPlaying = true;
    playbackState.isPaused = false;
    playbackState.lastRenderedLectureText = '';
    playbackState.lastRenderedAt = 0;
    if (playbackState.renderTimer) {
        clearTimeout(playbackState.renderTimer);
        playbackState.renderTimer = null;
    }

    // 鏄剧ず鎺堣灞曠ず鍖哄煙
    showLectureDisplayContainer();

    parseKnowledgePointsInContent(content);
    updateLectureDisplay(0);

    startSpeechSynthesis(content);

    document.getElementById('btn-play-content').disabled = true;
    document.getElementById('btn-pause-content').disabled = false;
    document.getElementById('btn-play-content').textContent = 'Playing...';

    showToast('Playback started', 'info');
}

function pauseContent() {
    if (!playbackState.isPlaying) {
        return;
    }

    if (playbackState.isPaused) {
        // 鎭㈠鎾斁
        playbackState.isPaused = false;
        speechSynthesis.resume();
        document.getElementById('btn-pause-content').textContent = '暂停';
        document.getElementById('btn-play-content').textContent = 'Playing...';
        showToast('继续播放', 'info');
    } else {
        // 鏆傚仠鎾斁
        playbackState.isPaused = true;
        speechSynthesis.pause();
        document.getElementById('btn-pause-content').textContent = '继续';
        document.getElementById('btn-play-content').textContent = 'Paused';
        showToast('Playback paused', 'info');
    }
}

function markAsLearnedManual() {
    markAsLearned();
}

// ==================== 缁冧範妯″紡 ====================

function resolvePracticeChapterId() {
    const practiceSelect = document.getElementById('practice-chapter-select');
    let selectedId = practiceSelect ? practiceSelect.value : '';

    if (!selectedId) {
        const learnSelect = document.getElementById('chapter-select');
        selectedId = learnSelect ? learnSelect.value : '';
        if (selectedId && practiceSelect) {
            practiceSelect.value = selectedId;
        }
    }

    return selectedId;
}

async function loadExercises() {
    const selectedId = resolvePracticeChapterId();
    const exerciseContent = document.getElementById('exercise-content');
    const toolbar = document.getElementById('exercise-toolbar');
    const desiredExerciseCount = 5;

    if (!selectedId) {
        showToast('请先选择练习章节', 'warning');
        return;
    }

    currentAnswer = null;
    currentExerciseIndex = 0;
    currentExerciseChapterId = selectedId;
    exerciseSelections = {};
    exerciseResults = {};

    if (exerciseContent) {
        exerciseContent.innerHTML = '<p class="loading">正在加载练习题...</p>';
    }
    if (toolbar) {
        toolbar.classList.add('hidden');
    }

    try {
        let chapterData = null;
        try {
            chapterData = await callAPI('/api/education/get-chapter', 'GET', { chapter_id: selectedId });
        } catch (chapterError) {
            console.warn('章节题库接口不可用，切换到学生题库接口:', chapterError);
        }

        if (chapterData && chapterData.success && chapterData.chapter) {
            const chapter = chapterData.chapter;
            const approvedBank = normalizeExerciseBank(chapter.approved_exercise_bank || []);
            const cachedBank = normalizeExerciseBank(chapter.exercise_bank || chapter.exercises || chapter);

            if (approvedBank.length >= desiredExerciseCount) {
                exerciseBank = approvedBank;
                currentExercise = exerciseBank[currentExerciseIndex];
                if (!currentExercise) throw new Error('题库为空');
                displayExercise(currentExercise);
                showToast(`已加载正式题库（${exerciseBank.length} 题）`, 'info');
            } else {
                
                const exerciseData = await callAPI('/api/student/generate-exercises', 'POST', {
                    chapter_id: selectedId,
                    chapter_title: chapter.title,
                    chapter_content: chapter.content,
                    count: desiredExerciseCount,
                    force_regenerate: cachedBank.length > 0 && cachedBank.length < desiredExerciseCount
                });

                if (exerciseData.success) {
                    const generatedApprovedBank = normalizeExerciseBank(exerciseData.approved_exercise_bank || []);
                    exerciseBank = exerciseData.approved && generatedApprovedBank.length
                        ? generatedApprovedBank
                        : normalizeExerciseBank(exerciseData.exercise_bank || exerciseData.exercises || exerciseData.exercise || exerciseData);
                    if (!exerciseBank.length) {
                        throw new Error(`题库数量不足：${exerciseBank.length} / ${desiredExerciseCount}`);
                    }
                    currentExercise = exerciseBank[currentExerciseIndex] || null;
                    if (!currentExercise) throw new Error('题库为空');
                    displayExercise(currentExercise);
                    const reviewText = exerciseData.review_pending ? '（待教师审核）' : '';
                    showToast(exerciseData.cached ? `已从题库加载${reviewText}` : `题库已预创建${reviewText}（${exerciseBank.length || 1} 题）`, 'success');
                } else {
                    throw new Error(exerciseData.error || '鐢熸垚澶辫触');
                }
            }
        } else {
            const exerciseData = await callAPI('/api/student/exercises', 'GET', { chapter_id: selectedId });
            if (exerciseData.success) {
                const apiApprovedBank = normalizeExerciseBank(exerciseData.approved_exercise_bank || []);
                exerciseBank = exerciseData.approved && apiApprovedBank.length
                    ? apiApprovedBank
                    : normalizeExerciseBank(exerciseData.exercise_bank || exerciseData.exercises || exerciseData.exercise || exerciseData);
                if (!exerciseBank.length) {
                    throw new Error(`题库数量不足：${exerciseBank.length} / ${desiredExerciseCount}`);
                }
                currentExercise = exerciseBank[currentExerciseIndex] || null;
                if (!currentExercise) throw new Error('题库为空');
                displayExercise(currentExercise);
                const reviewText = exerciseData.review_pending ? '（待教师审核）' : '';
                showToast(exerciseData.cached ? `已从题库加载${reviewText}` : `题库已预创建${reviewText}（${exerciseBank.length || 1} 题）`, 'success');
            } else {
                throw new Error(exerciseData.error || '加载题库失败');
            }
        }
    } catch (error) {
        console.error('加载练习题失败:', error);
        currentExercise = null;
        exerciseBank = [];
        if (exerciseContent) {
            exerciseContent.innerHTML = '<p class="placeholder">练习题加载失败，请刷新后重试。</p>';
        }
        showToast('加载练习题失败', 'error');
    }
}

function normalizeExerciseBank(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) {
        return payload.filter(isUsableExercise);
    }
    if (Array.isArray(payload.exercise_bank) && payload.exercise_bank.length) {
        return normalizeExerciseBank(payload.exercise_bank);
    }
    if (payload.exercises && Array.isArray(payload.exercises) && payload.exercises.length) {
        return normalizeExerciseBank(payload.exercises);
    }
    if (payload.questions && Array.isArray(payload.questions) && payload.questions.length) {
        return normalizeExerciseBank(payload.questions);
    }
    if (payload.items && Array.isArray(payload.items) && payload.items.length) {
        return normalizeExerciseBank(payload.items);
    }
    if (payload.data) {
        return normalizeExerciseBank(payload.data);
    }
    if (payload.question) {
        return isUsableExercise(payload) ? [payload] : [];
    }
    return [];
}

function isUsableExercise(item) {
    if (!item || !item.question) return false;
    const options = Array.isArray(item.options) ? item.options : [];
    if (options.length !== 4) return false;
    const text = [
        item.id,
        item.question,
        options.map(getOptionText).join(' ')
    ].join(' ').toLowerCase();
    const blocked = [
        'sample',
        '示例',
        '测试',
        '选项一',
        '选项二',
        '选项三',
        '选项四',
        'learningplan',
        'graph evidence',
        'current evidence',
        'knowledge graph constraint',
        '知识图谱约束',
        '图谱证据',
        '当前证据',
        '当前图谱依据不足',
        'which statement is directly stated in the material',
        'which option is correct',
        'what is this',
        'what is the key point about',
        'what does the source say about',
        'source passage',
        'see_formula',
        'see_table',
        '课堂导入',
        '授课文案',
        '教学目标',
        '启发提问',
        '教学要点',
        '小组讨论',
        '课后思考',
        'kg_gap',
        '当前图谱是否有足够证据'
    ];
    return !blocked.some(marker => text.includes(marker.toLowerCase()));
}

function getExerciseOptions(exercise) {
    return Array.isArray(exercise && exercise.options) ? exercise.options : [];
}

function isChoiceExercise(exercise) {
    return getExerciseOptions(exercise).length > 0;
}

function getOptionText(option) {
    if (option && typeof option === 'object') {
        return String(option.text || option.content || option.label || option.value || '').trim();
    }
    return String(option || '').trim();
}

function getExerciseKey(exercise, index) {
    const position = Number.isInteger(index) ? index : currentExerciseIndex;
    return String((exercise && exercise.id) || `exercise_${position}`);
}

function isMostlyEnglish(text) {
    const value = String(text || '');
    const latin = (value.match(/[A-Za-z]/g) || []).length;
    const cjk = (value.match(/[\u4e00-\u9fff]/g) || []).length;
    return latin > Math.max(12, cjk * 2);
}

function compactPracticeText(text, charLimit, wordLimit) {
    let value = String(text || '').replace(/\s+/g, ' ').trim();
    value = value.replace(/^[A-D][\s.、)）:：-]+/i, '').trim();
    if (!value) return '';
    if (containsLatexMath(value)) return value;

    if (isMostlyEnglish(value)) {
        const words = value.split(/\s+/);
        if (words.length > wordLimit) {
            value = words.slice(0, wordLimit).join(' ').replace(/[,.，。;；:：]+$/, '') + '...';
        }
    } else if (value.length > charLimit) {
        value = value.slice(0, charLimit).replace(/[,.，。;；:：]+$/, '') + '...';
    }

    return value;
}

function containsLatexMath(text) {
    return /\$\$|\\\[|\\\(|\\begin\{|\\frac|\\sum|\\prod|\\bar|\\overline|\\sigma|\\beta|\\delta|\\Delta|\\left|\\right|\$[^$\n]+\$/.test(String(text || ''));
}

function getOptionDisplayText(option) {
    return compactPracticeText(getOptionText(option), 420, 72);
}

function getOptionAnswer(option, index) {
    if (option && typeof option === 'object') {
        const key = option.key || option.answer || option.id || option.label;
        if (key) {
            const normalized = String(key).trim();
            if (/^[A-Z]$/i.test(normalized)) {
                return normalized.toUpperCase();
            }
        }
    }
    const text = getOptionText(option);
    const match = text.match(/^([A-Z])[\s.、)）:：-]/i);
    return match ? match[1].toUpperCase() : String.fromCharCode(65 + index);
}

function stripOptionPrefix(option) {
    return getOptionText(option).replace(/^[A-Z][\s.、)）:：-]+/i, '');
}

function displayExercise(exercise) {
    const exerciseContent = document.getElementById('exercise-content');

    if (exerciseContent && exercise) {
        const options = getExerciseOptions(exercise);
        const hasOptions = options.length > 0;
        const exerciseKey = getExerciseKey(exercise);
        const savedAnswer = exerciseSelections[exerciseKey] || '';
        const result = exerciseResults[exerciseKey] || null;
        const correctAnswer = String((result && result.correctAnswer) || exercise.correct_answer || exercise.answer || '').trim().toUpperCase();
        const questionText = compactPracticeText(exercise.question || '题目为空', 260, 52);
        let optionsHtml = '';
        if (hasOptions) {
            optionsHtml = options.map((opt, index) => {
                const answer = getOptionAnswer(opt, index);
                const selected = answer === savedAnswer;
                const classes = ['exercise-option'];
                if (selected) classes.push('selected');
                if ((result && result.revealed) || result) {
                    if (correctAnswer && answer === correctAnswer) classes.push('correct-choice');
                    if (selected && correctAnswer && answer !== correctAnswer) classes.push('incorrect-choice');
                }
                const displayText = getOptionDisplayText(opt);
                const fullText = stripOptionPrefix(opt);
                return `<button type="button" class="${classes.join(' ')}" data-answer="${escapeHtml(answer)}" aria-pressed="${selected ? 'true' : 'false'}" title="${escapeHtml(fullText)}">
                    <span class="exercise-option-key">${escapeHtml(answer)}</span>
                    <span class="exercise-option-text markdown-inline latex-auto">${renderRichInline(displayText)}</span>
                </button>`;
            }).join('');
        }

        exerciseContent.innerHTML = `
            <div class="exercise-meta">第 ${currentExerciseIndex + 1} / ${Math.max(1, exerciseBank.length || 1)} 题</div>
            <div class="exercise-question markdown-body" title="${escapeHtml(exercise.question || '')}">${renderRichText(questionText)}</div>
            ${hasOptions ? `
                <div class="exercise-options">
                    ${optionsHtml}
                </div>
                <input type="hidden" id="exercise-answer-input" value="${escapeHtml(savedAnswer)}">
                <div class="selected-answer-hint">${savedAnswer ? `已选择：${escapeHtml(savedAnswer)}` : '请选择一个选项'}</div>
            ` : `
                <textarea id="exercise-answer-input" class="exercise-answer-text" rows="4" placeholder="请输入答案"></textarea>
                <div class="selected-answer-hint">请输入答案后提交</div>
            `}
            ${renderExerciseFeedback(result)}
        `;

        exerciseContent.querySelectorAll('.exercise-option').forEach(button => {
            button.addEventListener('click', () => selectExerciseOption(button.dataset.answer));
        });

        const toolbar = document.getElementById('exercise-toolbar');
        if (toolbar) {
            toolbar.classList.remove('hidden');
        }
        updateExerciseToolbarState();
        queueLatexRender(exerciseContent);
    } else if (exerciseContent) {
        exerciseContent.innerHTML = '<p class="placeholder">请选择章节加载练习题</p>';
    }
}

function renderExerciseFeedback(result) {
    if (!result) return '';

    const stateClass = result.revealed || result.isCorrect ? 'correct' : 'incorrect';
    const title = result.revealed ? '参考答案' : (result.isCorrect ? '回答正确' : '再检查一下');
    const answerLine = result.correctAnswer ? `<div class="exercise-answer-state correct"><strong>正确答案：${renderRichInline(result.correctAnswer)}</strong></div>` : '';
    const yourAnswer = result.userAnswer ? `<div class="exercise-answer-state ${stateClass}">你的答案：${renderRichInline(result.userAnswer)}</div>` : '';
    const feedback = result.feedback ? `<div class="exercise-result-text markdown-body">${renderRichText(result.feedback)}</div>` : '';
    const explanation = result.explanation ? `
        <div class="exercise-explanation">
            <strong>解析：</strong>
            <div class="markdown-body">${renderRichText(result.explanation)}</div>
        </div>
    ` : '';

    return `
        <div class="exercise-feedback ${stateClass}">
            <div class="exercise-result-title"><strong>${title}</strong></div>
            ${yourAnswer}
            ${answerLine}
            ${feedback}
            ${explanation}
        </div>
    `;
}

function selectExerciseOption(answer) {
    if (currentExercise) {
        const existingResult = exerciseResults[getExerciseKey(currentExercise)];
        if (existingResult && existingResult.revealed) {
            showToast('已查看答案，本题选择已锁定', 'info');
            return;
        }
    }
    currentAnswer = String(answer || '').trim().toUpperCase();
    if (currentExercise) {
        const key = getExerciseKey(currentExercise);
        exerciseSelections[key] = currentAnswer;
        if (exerciseResults[key] && !exerciseResults[key].revealed) {
            delete exerciseResults[key];
        }
    }
    const answerInput = document.getElementById('exercise-answer-input');
    if (answerInput) {
        answerInput.value = currentAnswer;
    }
    document.querySelectorAll('#exercise-content .exercise-option').forEach(button => {
        button.classList.toggle('selected', button.dataset.answer === currentAnswer);
        button.classList.remove('correct-choice', 'incorrect-choice');
        button.setAttribute('aria-pressed', button.dataset.answer === currentAnswer ? 'true' : 'false');
    });
    const hint = document.querySelector('#exercise-content .selected-answer-hint');
    if (hint) {
        hint.textContent = `已选择：${currentAnswer}`;
    }
    const feedback = document.querySelector('#exercise-content .exercise-feedback');
    if (feedback) {
        feedback.remove();
    }
}

async function submitAnswer() {
    const answerInput = document.getElementById('exercise-answer-input');
    const selectedAnswer = currentAnswer || (answerInput ? answerInput.value.trim() : '');

    if (!selectedAnswer) {
        showToast(isChoiceExercise(currentExercise) ? '请先点击选择一个选项' : '请先输入答案', 'warning');
        return;
    }

    // 璋冪敤鏅鸿兘绛旀鍒ゆ柇
    await checkAnswer(selectedAnswer);
}

async function checkAnswer(userAnswer) {
    const selectedId = document.getElementById('practice-chapter-select').value;

    if (!currentExercise) {
        showToast('Please load an exercise first', 'warning');
        return;
    }

    // 璋冪敤鍚庣API杩涜鏅鸿兘绛旀鍒ゆ柇
    showToast('正在判断答案...', 'info');

    try {
        const result = await callAPI('/api/student/check-answer', 'POST', {
            exercise_id: currentExercise.id,
            question: currentExercise.question,
            answer: userAnswer,
            chapter_id: selectedId,
            correct_answer: currentExercise.correct_answer || currentExercise.answer || '',
            explanation: currentExercise.explanation || ''
        });

        if (result.success) {
            const isCorrect = result.is_correct;
            const score = result.correctness_score || 0;
            const exerciseKey = getExerciseKey(currentExercise);
            exerciseSelections[exerciseKey] = String(userAnswer || '').trim().toUpperCase();
            exerciseResults[exerciseKey] = {
                userAnswer: String(userAnswer || '').trim().toUpperCase(),
                isCorrect,
                score,
                feedback: result.feedback || '',
                explanation: result.explanation || currentExercise.explanation || '',
                correctAnswer: String(result.correct_answer || currentExercise.correct_answer || currentExercise.answer || '').trim().toUpperCase(),
                revealed: false
            };

            // 鏇存柊缁冧範鍘嗗彶
            exerciseHistory.push({
                exercise_id: currentExercise.id,
                question: currentExercise.question,
                user_answer: userAnswer,
                is_correct: isCorrect,
                correctness_score: score,
                feedback: result.feedback || '',
                answered_at: new Date().toISOString()
            });

            if (isCorrect) {
                showToast(result.feedback || 'Correct answer', 'success');
                updateExerciseProgress(100);
                showToast('本题练习完成', 'success');
            } else {
                showToast(result.feedback || 'Incorrect answer', 'error');
                updateExerciseProgress(0);
            }
            displayExercise(currentExercise);
        } else {
            showToast('判断答案失败', 'error');
        }
    } catch (error) {
        console.error('检查答案错误:', error);
        showToast('检查答案时发生错误', 'error');
    }
}

function showAnswer() {
    if (!currentExercise) {
        showToast('Please load an exercise first', 'warning');
        return;
    }

    const key = getExerciseKey(currentExercise);
    const correctAnswer = String(currentExercise.correct_answer || currentExercise.answer || '').trim().toUpperCase();
    exerciseResults[key] = {
        userAnswer: exerciseSelections[key] || currentAnswer || '',
        isCorrect: Boolean(exerciseSelections[key] && correctAnswer && exerciseSelections[key] === correctAnswer),
        feedback: '',
        explanation: currentExercise.explanation || '',
        correctAnswer: correctAnswer || '暂无',
        revealed: true
    };
    displayExercise(currentExercise);
}

function previousExercise() {
    if (exerciseBank.length > 0 && currentExerciseIndex > 0) {
        currentExerciseIndex -= 1;
        currentExercise = exerciseBank[currentExerciseIndex];
        currentAnswer = exerciseSelections[getExerciseKey(currentExercise)] || null;
        displayExercise(currentExercise);
        showToast(`已切换到第 ${currentExerciseIndex + 1} 题`, 'info');
        return;
    }

    showToast('已经是第一题', 'info');
}

function nextExercise() {
    if (exerciseBank.length > 0 && currentExerciseIndex < exerciseBank.length - 1) {
        currentExerciseIndex += 1;
        currentExercise = exerciseBank[currentExerciseIndex];
        currentAnswer = exerciseSelections[getExerciseKey(currentExercise)] || null;
        displayExercise(currentExercise);
        showToast(`已切换到第 ${currentExerciseIndex + 1} 题`, 'info');
        return;
    }

    showToast('题库已到最后一题', 'info');
}

function updateExerciseToolbarState() {
    const prevButton = document.getElementById('btn-prev-exercise');
    const nextButton = document.getElementById('btn-next-exercise');
    if (prevButton) {
        prevButton.disabled = currentExerciseIndex <= 0;
    }
    if (nextButton) {
        nextButton.disabled = !exerciseBank.length || currentExerciseIndex >= exerciseBank.length - 1;
    }
}

function updateExerciseProgress(progress) {
    exerciseProgress = progress;

    const progressBar = document.getElementById('exercise-progress');

    if (progressBar) {
        progressBar.style.width = `${progress}%`;
        progressBar.textContent = `完成度：${progress}%`;
    }
}

// ==================== 澶嶄範妯″紡 ====================

async function loadReviewData() {
    console.log('开始加载复习数据...');

    try {
        const data = await callAPI('/api/student/review', 'GET', {});

        console.log('复习数据响应:', data);

        if (data && data.success) {
            displayRecommendations(data.recommendations);
            showToast('Review data loaded', 'success');
        } else {
            console.error('API 返回失败:', data);
            showToast(data?.error || '加载复习数据失败', 'error');
        }
    } catch (error) {
        console.error('加载复习数据异常:', error);
        showToast('加载复习数据失败', 'error');
    }
}

function displayRecommendations(recommendations) {
    console.log('显示推荐数据:', recommendations);

    const recommendationsContent = document.getElementById('review-recommendations');

    console.log('找到推荐内容元素:', recommendationsContent);

    if (recommendationsContent) {
        if (!recommendations || recommendations.length === 0) {
            recommendationsContent.innerHTML = '<p class="placeholder">暂无复习建议</p>';
        } else {
            let html = '<ul class="recommendation-list">';
            recommendations.forEach((rec, index) => {
                html += `
                    <li class="recommendation-item">
                        <div class="rec-type">${rec.type}</div>
                        <div class="rec-content">${rec.content}</div>
                    </li>
                `;
            });
            html += '</ul>';
            recommendationsContent.innerHTML = html;
        }
    } else {
        console.error('未找到 review-recommendations 元素');
    }
}

// ==================== 闂瓟鍔熻兘 ====================

async function askQuestion() {
    const question = document.getElementById('question-input').value;
    const answerDisplay = document.getElementById('answer-display');

    if (!question) {
        showToast('Please enter a question', 'warning');
        return;
    }

    answerDisplay.innerHTML = '<p class="loading">Thinking...</p>';

    try {
        const data = await callAPI('/api/student/question', 'POST', { question });
        if (data.success) {
            displayAnswer(data.answer, data.warning);
            addToHistory(question, data.answer);
            document.getElementById('question-input').value = '';
            showToast('Answered', 'success');
        } else {
            throw new Error(data.error || data.detail || '回答失败');
        }
    } catch (error) {
        console.error('回答失败:', error);
        answerDisplay.innerHTML = '<p class="placeholder">回答失败，请稍后重试。</p>';
        showToast('回答失败', 'error');
    }
}

function displayAnswer(answer, warning) {
    const answerDisplay = document.getElementById('answer-display');
    if (!answerDisplay) return;

    const warningHtml = warning
        ? `<div class="answer-warning">${escapeHtml(warning)}</div>`
        : '';
    const text = String(answer || '').trim();

    answerDisplay.innerHTML = warningHtml + (text
        ? `<div class="answer-content markdown-body">${renderRichText(text)}</div>`
        : '<p class="placeholder">暂无回答</p>');
    queueLatexRender(answerDisplay);
}

function addToHistory(question, answer) {
    qaHistory.unshift({
        question: question,
        answer: answer,
        time: new Date().toLocaleString()
    });

    displayHistory();
}

function displayHistory() {
    const historyList = document.getElementById('history-list');

    if (qaHistory.length === 0) {
        historyList.innerHTML = '<p class="placeholder">暂无提问历史</p>';
    } else {
        let html = '';
        qaHistory.forEach((item, index) => {
            html += `
                <div class="history-item">
                    <div class="history-question">Q: ${renderRichInline(item.question)}</div>
                    <div class="history-answer">A: ${renderRichInline(String(item.answer || '').substring(0, 50))}...</div>
                    <div class="history-time">${escapeHtml(item.time)}</div>
                </div>
            `;
        });
        historyList.innerHTML = html;
        queueLatexRender(historyList);
    }
}

// ==================== 鐭ヨ瘑鍥捐氨 ====================

async function refreshGraph() {
    const graphContainer = document.getElementById('knowledge-graph');
    if (graphContainer) {
        graphContainer.innerHTML = `
            <div class="graph-placeholder">
                <p>知识图谱请在后端管理页查看，避免学生端卡顿。</p>
                <button onclick="openBackendGraphAdmin()" class="btn btn-small">打开后端知识图谱</button>
            </div>
        `;
    }
}

// 鍔犺浇鍥捐氨缁熻淇℃伅
async function loadGraphStatistics() {
    try {
        const response = await fetch(`${MAINTENANCE_API_BASE_URL}/api/maintenance/analytics`);
        const result = await response.json();

        if (result.success && result.data) {
            displayGraphStatistics(result.data);
        }
    } catch (error) {
        console.error('加载图谱统计失败:', error);
    }
}

// 鏄剧ず鍥捐氨缁熻淇℃伅
function displayGraphStatistics(stats) {
    
    const graphPanel = document.querySelector('.knowledge-graph-panel');
    if (!graphPanel) return;

        let statsContainer = document.getElementById('graph-stats-info');
    if (!statsContainer) {
        statsContainer = document.createElement('div');
        statsContainer.id = 'graph-stats-info';
        statsContainer.className = 'graph-stats-info';
        graphPanel.insertBefore(statsContainer, document.getElementById('knowledge-graph'));
    }

    const nodeStats = stats.nodes || {};
    const connectivity = stats.connectivity || {};
    const typeDist = stats.type_distribution || {};

    let statsHtml = '<div class="stats-grid">';
    statsHtml += `<div class="stat-item"><span class="stat-label">节点数:</span><span class="stat-value">${nodeStats.total || 0}</span></div>`;
    statsHtml += `<div class="stat-item"><span class="stat-label">关系数:</span><span class="stat-value">${stats.relations?.total || 0}</span></div>`;
    statsHtml += `<div class="stat-item"><span class="stat-label">连接密度:</span><span class="stat-value">${(connectivity.density || 0).toFixed(3)}</span></div>`;
    statsHtml += `<div class="stat-item"><span class="stat-label">连通分量:</span><span class="stat-value">${connectivity.connected_components || 0}</span></div>`;
    statsHtml += '</div>';

    
    if (Object.keys(typeDist).length > 0) {
        statsHtml += '<div class="type-distribution"><span class="type-dist-label">类型分布:</span>';
        for (const [type, count] of Object.entries(typeDist)) {
            statsHtml += `<span class="type-badge" style="background: ${getNodeColor(type)}">${type}: ${count}</span>`;
        }
        statsHtml += '</div>';
    }

    statsContainer.innerHTML = statsHtml;
}

function expandGraph() {
    const graphContainer = document.getElementById('knowledge-graph');
    if (graphContainer) {
        graphContainer.style.height = '600px';
        showToast('图谱已展开', 'info');
    }
}

function collapseGraph() {
    const graphContainer = document.getElementById('knowledge-graph');
    if (graphContainer) {
        graphContainer.style.height = '400px';
        showToast('Graph collapsed', 'info');
    }
}

function displayGraph(graphData) {
    const graphContainer = document.getElementById('knowledge-graph');

    if (graphContainer && graphData && graphData.nodes) {
        const normalized = normalizeStudentGraph(graphData);
        window.studentGraphData = normalized;
        const nodeById = new Map(normalized.nodes.map(node => [node.id, node]));
        const visibleNodes = normalized.nodes.slice(0, 80);
        const visibleNodeIds = new Set(visibleNodes.map(node => node.id));
        const visibleEdges = normalized.edges
            .filter(edge => visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to))
            .slice(0, 80);

        let html = '<div class="student-graph-readable">';
        html += '<div class="student-graph-summary">';
        html += `<span>节点 ${normalized.nodes.length}</span>`;
        html += `<span>关系 ${normalized.edges.length}</span>`;
        html += '</div>';
        html += '<div class="student-graph-node-list">';
        visibleNodes.forEach(node => {
            const color = getNodeColor(node.type);
            html += `
                <button class="student-graph-node" data-node-id="${escapeHtml(node.id)}"
                        onclick="showNodeDetail(this.dataset.nodeId)"
                        style="border-left-color:${color}">
                    <span class="student-graph-node-title">${escapeHtml(node.label)}</span>
                    <span class="student-graph-node-type">${escapeHtml(node.type || 'concept')}</span>
                </button>
            `;
        });
        html += '</div>';

        if (visibleEdges.length > 0) {
            html += '<div class="student-graph-relations">';
            visibleEdges.forEach(edge => {
                const from = nodeById.get(edge.from);
                const to = nodeById.get(edge.to);
                html += `
                    <div class="student-graph-relation">
                        <span>${escapeHtml(from?.label || edge.from)}</span>
                        <b>${escapeHtml(edge.label || edge.type || 'related')}</b>
                        <span>${escapeHtml(to?.label || edge.to)}</span>
                    </div>
                `;
            });
            html += '</div>';
        }
        html += '</div>';
        graphContainer.innerHTML = html;
    } else {
        graphContainer.innerHTML = '<p class="placeholder">点击“刷新图谱”加载知识图谱</p>';
    }
}

function normalizeStudentGraph(data) {
    const nodes = (data.nodes || []).map(node => {
        const metadata = node.metadata || {};
        return {
            id: String(node.id || metadata.id || ''),
            label: node.label || metadata.label || node.content || node.id || '未命名节点',
            type: node.type || metadata.type || 'concept',
            content: node.content || metadata.description || ''
        };
    }).filter(node => node.id);

    const edges = (data.edges || data.relations || []).map(edge => {
        const metadata = edge.metadata || {};
        return {
            from: String(edge.from || edge.source || edge.source_id || ''),
            to: String(edge.to || edge.target || edge.target_id || ''),
            label: edge.label || edge.type || edge.relation_type || metadata.description || 'related'
        };
    }).filter(edge => edge.from && edge.to);

    return { nodes, edges };
}

function showNodeDetail(nodeId) {
    const graph = window.studentGraphData;
    const node = graph && graph.nodes ? graph.nodes.find(item => item.id === nodeId) : null;
    if (!node) {
        showToast(`节点 ID: ${nodeId}`, 'info');
        return;
    }
    const text = `${node.label}${node.type ? ' · ' + node.type : ''}${node.content ? '\n' + node.content.slice(0, 160) : ''}`;
    showToast(text, 'info');
}

function getNodeColor(type) {
    const colors = {
        'chapter': '#667eea',
        'concept': '#10b981',
        'note': '#f59e0b',
        'exercise': '#3b82f6'
    };
    return colors[type] || '#6b7280';
}

// ==================== 娴獥鍔熻兘 ====================

function toggleQaWindow() {
    const qaWindow = document.getElementById('qa-float-window');
    if (qaWindow) {
        if (qaWindow.classList.contains('hidden')) {
            qaWindow.style.left = '';
            qaWindow.style.top = '';
            qaWindow.style.right = '';
            qaWindow.style.bottom = '';
            qaWindow.classList.remove('hidden');
            document.body.classList.add('qa-panel-open');
        } else {
            qaWindow.classList.add('hidden');
            document.body.classList.remove('qa-panel-open');
        }
    }
}

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

function refreshQaWindow() {
    const qaBody = document.getElementById('qa-float-body');

    // 娓呯┖鍘嗗彶璁板綍
    qaHistory = [];
    displayHistory();

    showToast('Q&A window refreshed', 'info');
}

// ==================== 宸ュ叿鍑芥暟 ====================

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');

    if (toast && toastMessage) {
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
            }, 3000);
        }, 100);
    }
}

// 瀛︾敓绔幏鍙栬竟棰滆壊
function getEdgeColor(type) {
    const colors = {
        'contains': '#f59e0b',
        'precedes': '#10b981',
        'related': '#6b7280',
        '璇箟鐩稿叧': '#3b82f6',
        'belongs_to': '#8b5cf6',
        'based_on': '#10b981'
    };
    return colors[type] || '#9ca3af';
}

// ==================== 浜嬩欢鐩戝惉 ====================

document.addEventListener('DOMContentLoaded', function() {
    // 鍔犺浇绔犺妭鍒楄〃
    loadChapterList();

    // 鍒锋柊鐭ヨ瘑鍥捐氨
    refreshGraph();

    
    const chapterSelect = document.getElementById('chapter-select');
    if (chapterSelect) {
        chapterSelect.onchange = onChapterChange;
    }

    
    const practiceChapterSelect = document.getElementById('practice-chapter-select');
    if (practiceChapterSelect) {
        practiceChapterSelect.onchange = loadExercises;
    }

    
    const questionInput = document.getElementById('question-input');
    if (questionInput) {
        questionInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                askQuestion();
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

    
    const exerciseInput = document.querySelector('#exercise-content input');
    if (exerciseInput) {
        exerciseInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                submitAnswer();
            }
        });
    }

    // 鍒濆鍖栨嫋鎷藉姛鑳?    initDragFunctionality();
});

// ==================== 鎷栨嫿鍔熻兘 ====================

function initDragFunctionality() {
    const qaWindow = document.getElementById('qa-float-window');
    const lectureFloat = document.getElementById('lecture-float-window');

    if (lectureFloat) makeDraggable(lectureFloat, document.querySelector('.lecture-float-header'));
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

// ==================== 鎺堣灞曠ず鍔熻兘 ====================

// 鏄剧ず鎺堣灞曠ず瀹瑰櫒
function showLectureDisplayContainer() {
    const displayContainer = document.getElementById('lecture-display-container');
    const originalWrapper = document.getElementById('original-content-wrapper');

    if (displayContainer) {
        displayContainer.classList.remove('hidden');
    }
    if (originalWrapper) {
        originalWrapper.classList.add('hidden');
    }
}

// 鍒囨崲鏄剧ず鍏ㄩ儴/閮ㄥ垎鍐呭
function toggleFullContent() {
    const btn = document.getElementById('btn-show-full-content');
    const displayDiv = document.getElementById('lecture-display-text');

    if (playbackState.showFullContent) {
        // 鍒囨崲鍒版樉绀洪儴鍒嗗唴瀹?        playbackState.showFullContent = false;
        btn.textContent = '显示全部';
        displayDiv.classList.remove('show-full');
        displayDiv.classList.add('show-partial');
        updateLectureDisplay(playbackState.currentPosition);
    } else {
        // 鍒囨崲鍒版樉绀哄叏閮ㄥ唴瀹?        playbackState.showFullContent = true;
        btn.textContent = '显示部分';
        displayDiv.classList.remove('show-partial');
        displayDiv.classList.add('show-full');
        renderFullContent();
    }
}

function parseKnowledgePointsInContent(content) {
    knowledgePoints = [];

    // 棣栧厛鑾峰彇鐭ヨ瘑鍥捐氨鏁版嵁
    fetchGraphData().then(data => {
        if (data && data.nodes) {
            graphData = data;
            // 涓烘瘡涓妭鐐瑰湪鍐呭涓煡鎵惧嚭鐜扮殑浣嶇疆
            data.nodes.forEach(node => {
                const positions = findKeywordPositions(content, node.label);
                if (positions.length > 0) {
                    knowledgePoints.push({
                        keyword: node.label,
                        nodeId: node.id,
                        positions: positions,
                        type: node.type
                    });
                }
            });

            knowledgePoints.sort((a, b) => a.positions[0] - b.positions[0]);
        }
    });
}

function findKeywordPositions(content, keyword) {
    const positions = [];
    let index = content.indexOf(keyword);
    while (index !== -1) {
        positions.push(index);
        index = content.indexOf(keyword, index + 1);
    }
    return positions;
}

// 鑾峰彇鐭ヨ瘑鍥捐氨鏁版嵁
async function fetchGraphData() {
    try {
        const response = await fetch(`${MAINTENANCE_API_BASE_URL}/api/maintenance/graph`, { cache: 'no-store' });
        const result = await response.json();
        if (response.ok && result.success) {
            return result.data;
        }
    } catch (error) {
        console.error('获取知识图谱数据失败:', error);
    }
    return null;
}

function startSpeechSynthesis(content) {
    if (!window.speechSynthesis) {
        showToast('你的浏览器不支持语音播放功能', 'error');
        return;
    }

    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // 鐩戝惉杈圭晫浜嬩欢锛堣幏鍙栨挱鏀句綅缃級
    utterance.onboundary = (event) => {
        if (event.name === 'word') {
            playbackState.currentPosition = event.charIndex;
            scheduleLectureDisplayUpdate(event.charIndex);
        }
    };

    // 鎾斁缁撴潫
    utterance.onend = () => {
        playbackState.isPlaying = false;
        playbackState.isPaused = false;
        document.getElementById('btn-play-content').disabled = false;
        document.getElementById('btn-pause-content').disabled = true;
        document.getElementById('btn-play-content').textContent = '播放讲解';
        if (playbackState.renderTimer) {
            clearTimeout(playbackState.renderTimer);
            playbackState.renderTimer = null;
        }
        clearAllHighlights();
        showToast('讲解播放完成', 'success');
    };

    // 鎾斁閿欒
    utterance.onerror = (error) => {
        console.error('语音播放错误:', error);
        playbackState.isPlaying = false;
        document.getElementById('btn-play-content').disabled = false;
        document.getElementById('btn-pause-content').disabled = true;
        document.getElementById('btn-play-content').textContent = '播放讲解';
        showToast('语音播放出错', 'error');
    };

    playbackState.currentUtterance = utterance;
    speechSynthesis.speak(utterance);
}

// 鏇存柊鎺堣鏂囨鏄剧ず
function scheduleLectureDisplayUpdate(position) {
    const now = performance.now();
    playbackState.currentPosition = position;

    if (now - playbackState.lastRenderedAt >= 280) {
        updateLectureDisplay(position);
        updateGraphHighlights(position);
        return;
    }

    if (playbackState.renderTimer) {
        return;
    }

    playbackState.renderTimer = setTimeout(() => {
        playbackState.renderTimer = null;
        updateLectureDisplay(playbackState.currentPosition);
        updateGraphHighlights(playbackState.currentPosition);
    }, 280);
}

function updateLectureDisplay(currentPosition) {
    const displayDiv = document.getElementById('lecture-display-text');
    const content = playbackState.fullContent;

    if (!content) return;

    if (playbackState.showFullContent) {
        renderFullContentWithHighlights(content, currentPosition);
    } else {
        
        const range = 50;
        const startPos = Math.max(0, currentPosition - range);
        const endPos = Math.min(content.length, currentPosition + range);
        const displayText = content.substring(startPos, endPos);

        renderPartialContentWithHighlights(displayText, currentPosition, startPos);
    }
}

function renderFullContent() {
    const content = playbackState.fullContent;
    renderFullContentWithHighlights(content, playbackState.currentPosition);
}

function renderFullContentWithHighlights(content, currentPosition) {
    const displayDiv = document.getElementById('lecture-display-text');
    renderLectureText(displayDiv, content || '');
}

function renderPartialContentWithHighlights(partialText, currentPosition, contentOffset) {
    const displayDiv = document.getElementById('lecture-display-text');
    renderLectureText(displayDiv, partialText || '');
}

function renderLectureText(displayDiv, text) {
    if (!displayDiv || playbackState.lastRenderedLectureText === text) {
        playbackState.lastRenderedAt = performance.now();
        return;
    }
    playbackState.lastRenderedLectureText = text;
    playbackState.lastRenderedAt = performance.now();
    setRichContent(displayDiv, text);
}

// 鏇存柊鐭ヨ瘑鍥捐氨楂樹寒
function updateGraphHighlights(currentPosition) {
    const activeNodeIds = new Set();

    knowledgePoints.forEach(point => {
        point.positions.forEach(pos => {
            if (currentPosition >= pos && currentPosition <= pos + point.keyword.length) {
                activeNodeIds.add(point.nodeId);
            }
        });
    });

    // 鏇存柊楂樹寒鏄剧ず
    highlightGraphNodes(activeNodeIds);
}

// 楂樹寒鐭ヨ瘑鍥捐氨鑺傜偣
function highlightGraphNodes(activeNodeIds) {
    document.querySelectorAll('#knowledge-graph .node').forEach(node => {
        node.classList.remove('highlighted');
        node.style.transform = '';
    });

    // 楂樹寒娲昏穬鑺傜偣
    activeNodeIds.forEach(nodeId => {
        const nodeElement = document.getElementById(`node-${nodeId}`);
        if (nodeElement) {
            nodeElement.classList.add('highlighted');

            nodeElement.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    });
}

function clearAllHighlights() {
    // 娓呴櫎鏂囨楂樹寒
    document.querySelectorAll('.knowledge-keyword').forEach(kw => {
        kw.classList.remove('active');
    });

    // 娓呴櫎鍥捐氨楂樹寒
    document.querySelectorAll('#knowledge-graph .node').forEach(node => {
        node.classList.remove('highlighted');
        node.style.transform = '';
    });
}

// HTML杞箟
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 璁剧疆鍔熻兘 ====================

// 鍒囨崲璁剧疆寮圭獥
function toggleSettingsWindow() {
    const settingsModal = document.getElementById('settings-modal');
    if (settingsModal) {
        if (settingsModal.classList.contains('hidden')) {
            settingsModal.classList.remove('hidden');
            testApiKey();
        } else {
            closeSettingsModal();
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
    localStorage.removeItem('deepseek_api_key');
    localStorage.removeItem('claude_api_key');
    showToast('请在项目根目录 .env 中修改 DeepSeek 配置，然后重启 start.bat', 'info');
    closeSettingsModal();
}

// 娴嬭瘯 API 瀵嗛挜
async function testApiKey() {
    showToast('正在检测后端配置...', 'info');

    try {
        const response = await fetch(`${EDUCATION_API_BASE_URL}/api/config-status`, { cache: 'no-store' });
        const result = await response.json();
        const statusText = document.getElementById('config-status-text');
        const configured = Boolean(result.deepseek_api_key_configured);
        const message = configured
            ? `后端已读取 .env：flash=${result.flash_model || '-'}，pro=${result.pro_model || '-'}`
            : '后端未读取到 DEEPSEEK_API_KEY，请修改项目根目录 .env 后重启 start.bat';

        if (statusText) {
            statusText.textContent = message;
        }
        showToast(message, configured ? 'success' : 'warning');
    } catch (error) {
        console.error('配置检测失败:', error);
        showToast('配置检测失败，请确认后端服务已启动', 'error');
    }
}

// 鍒囨崲 API 瀵嗛挜鏄剧ず/闅愯棌
function toggleApiKeyVisibility() {
    const apiKeyInput = document.getElementById('deepseek-api-key');
    if (!apiKeyInput || !('type' in apiKeyInput)) return;
    if (apiKeyInput.type === 'password') {
        apiKeyInput.type = 'text';
    } else {
        apiKeyInput.type = 'password';
    }
}

// 鑾峰彇褰撳墠鐢ㄦ埛鐨?API 瀵嗛挜
function getStoredApiKey() {
    return '';
}

function getUserApiKey() {
    return '';
}



