/* READY browser client: server-owned actions and confirmations only. */
(function () {
  'use strict';

  const API_ROOT = '/api';
  const state = {
    userId: null,
    sessionId: null,
    csrfToken: null,
    users: [],
    actions: [],
    scheduleFormConfig: null,
    activeDraft: null,
    busy: false,
    bootstrapped: false,
    agent: null,
  };

  const dom = {
    userSelect: document.querySelector('#demo-user'),
    accountSummary: document.querySelector('#account-summary'),
    balanceValue: document.querySelector('#account-heading'),
    balanceCaption: document.querySelector('#balance-caption'),
    conversation: document.querySelector('#conversation'),
    activeArea: document.querySelector('#active-area'),
    actionList: document.querySelector('#action-list'),
    form: document.querySelector('#chat-form'),
    input: document.querySelector('#chat-input'),
    send: document.querySelector('#send-button'),
    environmentLabel: document.querySelector('#environment-label'),
    environmentDetail: document.querySelector('#environment-detail'),
    connection: document.querySelector('#connection-status'),
    footerStatus: document.querySelector('#footer-status'),
    toastRegion: document.querySelector('#toast-region'),
    textSize: document.querySelector('#text-size-toggle'),
    agentMode: document.querySelector('#agent-mode'),
    agentDetail: document.querySelector('#agent-detail'),
    agentActivity: document.querySelector('#agent-activity'),
    agentTrace: document.querySelector('#agent-trace'),
  };

  const LABELS = {
    operation: 'العملية',
    recipient: 'المستفيد',
    recipient_name: 'المستفيد',
    biller: 'الجهة المستلمة',
    provider: 'المزوّد',
    account: 'الحساب',
    account_display: 'الحساب',
    account_identifier: 'الحساب',
    amount: 'المبلغ',
    currency: 'العملة',
    fee: 'الرسوم',
    total: 'إجمالي الخصم',
    total_debit: 'إجمالي الخصم',
    funding_source: 'مصدر الأموال',
    quote_expiry: 'صلاحية العرض',
    quote_expires_at: 'صلاحية العرض',
    expires_at: 'تنتهي المراجعة',
    reference: 'المرجع',
    status: 'الحالة',
    transaction_id: 'معرّف العملية',
    due_date: 'تاريخ الاستحقاق',
    scheduled_for: 'موعد التذكير والتحضير',
    timezone: 'المنطقة الزمنية',
    recurrence: 'التكرار',
    authorization_mode: 'نمط الصلاحية',
    execution_mode: 'آلية التنفيذ',
    next_occurrence: 'الموعد التالي',
    schedule_id: 'معرّف الموعد التجريبي',
    debit_minor: 'الخصم الآن',
  };

  // Public fixture choices only. The server still authorizes every session.
  const FALLBACK_DEMO_USERS = [
    { id: 'demo_amina', label: 'أمينة — حساب تجريبي' },
    { id: 'demo_hassan', label: 'حسن — حساب تجريبي' },
    { id: 'demo_operator', label: 'مشغّل — جلسة منفصلة' },
  ];
  function element(tag, options) {
    const node = document.createElement(tag);
    if (!options) return node;
    if (options.className) node.className = options.className;
    if (options.text !== undefined && options.text !== null) node.textContent = String(options.text);
    if (options.attrs) {
      Object.entries(options.attrs).forEach(([name, value]) => {
        if (value !== undefined && value !== null) node.setAttribute(name, String(value));
      });
    }
    return node;
  }

  function text(value, fallback) {
    return value === undefined || value === null || value === '' ? (fallback || '—') : String(value);
  }

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function apiError(message, status) {
    const error = new Error(message || 'تعذر إكمال الطلب الآن.');
    error.status = status;
    return error;
  }

  async function request(path, options) {
    const settings = options || {};
    const sessionHeaders = settings.useSession === false || !state.sessionId
      ? {}
      : {
          'X-Demo-Session': state.sessionId,
          ...(state.csrfToken ? { 'X-CSRF-Token': state.csrfToken } : {}),
        };
    const response = await fetch(`${API_ROOT}${path}`, {
      headers: {
        Accept: 'application/json',
        ...(settings.body ? { 'Content-Type': 'application/json' } : {}),
        ...sessionHeaders,
        ...(settings.headers || {}),
      },
      credentials: 'same-origin',
      method: settings.method,
      body: settings.body,
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* handled below */ }
    if (!response.ok) {
      const detail = payload && (payload.message || payload.detail || (typeof payload.error === 'object' ? (payload.error.message || payload.error.code) : payload.error));
      const error = apiError(detail || 'تعذر الاتصال بالخدمة التجريبية.', response.status);
      error.code = payload && payload.error && payload.error.code;
      const localized = {
        INSUFFICIENT_FUNDS: 'الرصيد ما يكفي للمبلغ والرسوم. راجع الرصيد أو عدّل المبلغ؛ ما تمت دفعة جديدة.',
        INSUFFICIENT_BALANCE: 'الرصيد ما يكفي للمبلغ والرسوم. راجع الرصيد أو عدّل المبلغ؛ ما تمت دفعة جديدة.',
        MODEL_NOT_CONFIGURED: 'اتصال النموذج يحتاج إعداد على الكمبيوتر. افتح دليل إعداد النموذج؛ تگدر تستخدم أزرار الخدمات هسه.',
        MODEL_AUTH_FAILED: 'خدمة النموذج رفضت مفتاح API المحفوظ بالخادم. راجع إعدادات المفتاح على الكمبيوتر.',
        MODEL_RATE_LIMIT: 'خدمة النموذج وصلت لحد الطلبات أو الرصيد. جرّب لاحقاً أو استخدم أزرار الخدمات.',
        MODEL_TIMEOUT: 'النموذج تأخر بالرد. ما نفذنا أي دفعة. تگدر تحاول مرة ثانية.',
        MODEL_UNAVAILABLE: 'تعذر الوصول للنموذج. تحقق من اتصال الكمبيوتر وإعدادات الخدمة.',
        MODEL_INVALID_ARGUMENTS: 'رد النموذج ما حدد تفاصيل صالحة. ما نفذنا أي دفعة؛ وضّح طلبك أو استخدم الأزرار.',
        MODEL_TOOL_FORBIDDEN: 'النموذج طلب إجراء غير مسموح. ما نفذنا أي دفعة.',
        MODEL_AMBIGUOUS_RECIPIENT: 'المستلم مو واضح. اكتب الاسم الكامل من جهات الاتصال حتى نجهز المراجعة.',
        TRANSACTION_NOT_FOUND: 'ما لقينا هالمرجع ضمن عمليات حسابك التجريبي. تأكد من المرجع والمستخدم المختار.',
      };
      if (localized[error.code]) error.message = localized[error.code];
      throw error;
    }
    return payload || {};
  }
  const api = {
    bootstrap(userId) {
      const query = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
      return request(`/bootstrap${query}`, { useSession: false });
    },
    chat(message) {
      return request('/chat', { method: 'POST', body: JSON.stringify({ message }) });
    },
    action(actionId, payload) {
      return request(`/actions/${encodeURIComponent(actionId)}`, {
        method: 'POST',
        body: JSON.stringify(payload || {}),
      });
    },
    confirmDraft(draft) {
      // The approval credential is deliberately HttpOnly; the client never sees it.
      return request(`/drafts/${encodeURIComponent(draft.id)}/confirm`, { method: 'POST', body: '{}' });
    },
    confirmScheduleDraft(draft) {
      // Schedule drafts use a separate cookie and endpoint; a text reply never confirms either lifecycle.
      return request(`/schedule-drafts/${encodeURIComponent(draft.id)}/confirm`, { method: 'POST', body: '{}' });
    },
    cancelScheduleDraft(draft) {
      return request(`/schedule-drafts/${encodeURIComponent(draft.id)}/cancel`, { method: 'POST', body: '{}' });
    },
    cancelDraft(draft) {
      return request(`/drafts/${encodeURIComponent(draft.id)}/cancel`, { method: 'POST', body: '{}' });
    },
    scheduleDraftStatus(draftId) {
      return request(`/schedule-drafts/${encodeURIComponent(draftId)}/status`);
    },
    transactionStatus(transactionId) {
      return request(`/transactions/${encodeURIComponent(transactionId)}/status`);
    },
    draftStatus(draftId) {
      return request(`/drafts/${encodeURIComponent(draftId)}/status`);
    },
  };

  function setConnection(stateName, detail) {
    const labels = {
      ready: 'متصل بالخدمة',
      loading: 'جارِ المعالجة',
      offline: 'الخدمة غير متاحة',
    };
    dom.connection.textContent = labels[stateName] || labels.ready;
    dom.connection.classList.toggle('is-problem', stateName === 'offline');
    dom.footerStatus.textContent = detail || (stateName === 'offline' ? 'لم نتمكن من الوصول إلى الخادم المحلي.' : state.agent && state.agent.mode === 'LIVE_MODEL' ? 'المحفظة محاكاة؛ تفسير الطلب يتصل بمزوّد النموذج المهيأ.' : 'تفسير محلي ثابت؛ لا توجد اتصالات بنموذج خارجي.');
  }

  function setJourney(step) {
    document.querySelectorAll('[data-step]').forEach((node) => {
      node.classList.toggle('is-current', node.dataset.step === step);
      if (node.dataset.step === step) node.setAttribute('aria-current', 'step');
      else node.removeAttribute('aria-current');
    });
  }

  function renderAgent(agent) {
    if (!agent) return;
    state.agent = agent;
    const live = agent.mode === 'LIVE_MODEL';
    const success = agent.last_request === 'succeeded';
    dom.agentMode.textContent = !live ? 'تجربة محلية · بدون نموذج' : !agent.configured ? 'النموذج يحتاج إعداد' : success ? 'تم الرد من النموذج' : agent.last_request === 'failed' ? 'تعذر رد النموذج' : 'اتصال النموذج مهيأ';
    dom.agentMode.classList.toggle('is-live', live && agent.configured);
    dom.agentDetail.textContent = !live
      ? 'التفسير هنا بقواعد ثابتة. فعّل اتصال النموذج من إعدادات الخادم لتجربة الأدوات الذكية.'
      : !agent.configured
        ? 'إعداد النموذج يتم على الكمبيوتر. مفاتيح API ما تنكتب بالمحادثة أو داخل التطبيق.'
        : `النموذج: ${agent.model || '—'} · ${success ? 'الأدوات نفّذت قراءات أو تجهيز مراجعة فقط؛ القرار الأخير إلك.' : 'الاتصال الفعلي ينفحص عند إرسال طلب. كل عمليات المحفظة تبقى محاكاة.'}`;
    const names = { LIST_CONTACTS: 'قرأ جهات اتصال حسابك', LIST_BILLS: 'قرأ الفواتير المحفوظة', VIEW_BALANCE: 'فحص الرصيد', VIEW_HISTORY: 'قرأ سجل العمليات', OPEN_TRANSFER: 'جهز مراجعة تحويل', OPEN_BILL_PAYMENT: 'جهز مراجعة الفاتورة', OPEN_SCHEDULED_TRANSFER: 'جهز إعداد موعد', ASK_USER: 'طلب توضيح منك', VIEW_WALLET_INSIGHTS: 'حسب ملخص المحفظة', PREPARE_SUPPORT_REQUEST: 'جهز مسودة دعم للمراجعة', CHECK_PAYMENT_STATUS: 'فحص حالة نفس العملية', SHOW_RECEIVE_QR: 'أظهر رمز الاستلام' };
    dom.agentTrace.replaceChildren();
    asArray(agent.trace).forEach((item) => dom.agentTrace.append(element('li', { text: `${['error', 'rejected'].includes(item.status) ? 'لم ينفذ: ' : ''}${names[item.tool] || 'إجراء مسجل'}${['error', 'rejected'].includes(item.status) ? ' — يحتاج توضيح أو معالجة' : ''}` })));
    dom.agentActivity.hidden = !dom.agentTrace.childElementCount;
  }

  function setBusy(isBusy, message) {
    state.busy = isBusy;
    dom.send.disabled = isBusy || !state.bootstrapped;
    dom.input.disabled = isBusy || !state.bootstrapped;
    dom.userSelect.disabled = isBusy || state.users.length === 0;
    setConnection(isBusy ? 'loading' : (state.bootstrapped ? 'ready' : 'offline'), message);
  }

  function showToast(message, kind) {
    dom.toastRegion.replaceChildren();
    const toast = element('div', { className: `toast${kind === 'error' ? ' is-error' : ''}`, text: message, attrs: { role: 'status' } });
    dom.toastRegion.append(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function scrollConversation() {
    window.requestAnimationFrame(() => {
      dom.conversation.scrollTop = dom.conversation.scrollHeight;
    });
  }

  function appendMessage(kind, message, actions) {
    const article = element('article', { className: `message message-${kind}` });
    const label = element('div', { className: 'message-label', text: kind === 'user' ? 'أنت' : kind === 'system' ? 'تنبيه' : 'READY' });
    const body = element('p', { text: text(message, kind === 'assistant' ? 'تمت معالجة طلبك.' : '') });
    article.append(label, body);
    if (asArray(actions).length) {
      const actionContainer = element('div', { className: 'message-actions', attrs: { 'aria-label': 'إجراءات متاحة' } });
      actions.forEach((action) => actionContainer.append(createActionButton(normalizeAction(action))));
      article.append(actionContainer);
    }
    dom.conversation.append(article);
    scrollConversation();
    return article;
  }

  function appendServerMessages(messages) {
    let rendered = false;
    asArray(messages).forEach((message) => {
      if (typeof message === 'string') {
        appendMessage('assistant', message, []);
        rendered = true;
        return;
      }
      if (!message || typeof message !== 'object') return;
      appendMessage(message.role === 'user' ? 'user' : 'assistant', message.message || message.text || message.content, message.actions || []);
      rendered = true;
    });
    return rendered;
  }

  function appendClarification(clarification, promptAlreadyRendered) {
    if (!clarification) return false;
    const prompt = clarification.prompt || clarification.message || 'احتاج معلومة إضافية قبل المتابعة.';
    const article = promptAlreadyRendered && dom.conversation.lastElementChild
      ? dom.conversation.lastElementChild
      : appendMessage('assistant', prompt, []);
    const choices = asArray(clarification.choices);
    if (!choices.length) return true;
    const container = element('div', { className: 'message-actions', attrs: { 'aria-label': 'اختر إجابة' } });
    choices.forEach((choice) => {
      const choiceText = text(choice && (choice.label || choice.text || choice.id), 'اختيار');
      const button = element('button', { className: 'action-button', text: choiceText, attrs: { type: 'button' } });
      button.addEventListener('click', () => {
        if (state.busy) return;
        dom.input.value = choiceText;
        if (dom.form.requestSubmit) dom.form.requestSubmit();
        else dom.form.dispatchEvent(new Event('submit', { cancelable: true }));
      });
      container.append(button);
    });
    article.append(container);
    scrollConversation();
    return true;
  }
  function normalizeAction(action) {
    return {
      id: action.id || action.action_id || action.actionId || '',
      label: action.label_ar || action.label || action.title || action.id || 'خدمة',
      description: action.description || action.subtitle || '',
      enabled: action.enabled !== false && action.available !== false,
      confirmationRequired: Boolean(action.confirmation_required || action.requires_confirmation),
      raw: action,
    };
  }

  function createActionButton(action) {
    const button = element('button', {
      className: 'action-button',
      attrs: {
        type: 'button',
        'data-action-id': action.id,
        'aria-disabled': String(!action.enabled),
        title: action.description || action.label,
      },
    });
    const label = element('span', { text: action.label });
    const type = element('span', { className: 'action-type', text: action.confirmationRequired ? 'يتطلب مراجعة' : 'عرض' });
    button.append(label, type);
    if (!action.enabled || !action.id) button.disabled = true;
    button.addEventListener('click', () => handleAction(action));
    return button;
  }

  function renderActions(actions) {
    state.actions = asArray(actions).map(normalizeAction).filter((action) => action.id);
    dom.actionList.replaceChildren();
    if (!state.actions.length) {
      dom.actionList.append(element('p', { className: 'empty-actions', text: 'لا توجد خدمات مسجلة متاحة لهذه الجلسة.' }));
      return;
    }
    state.actions.forEach((action) => dom.actionList.append(createActionButton(action)));
  }

  function normalizeUsers(payload) {
    const candidates = payload.users || payload.demo_users || payload.sessions || [];
    const normalized = asArray(candidates).map((user) => ({
      id: user.id || user.user_id || user.userId,
      label: user.label || user.display_name || user.name || user.id || user.user_id,
      role: user.role || '',
    })).filter((user) => user.id);
    return normalized.length ? normalized : FALLBACK_DEMO_USERS;
  }

  function renderUsers(users, selectedId) {
    state.users = users;
    dom.userSelect.replaceChildren();
    users.forEach((user) => {
      const option = element('option', { text: user.role ? `${user.label} — ${user.role}` : user.label, attrs: { value: user.id } });
      option.selected = user.id === selectedId;
      dom.userSelect.append(option);
    });
    dom.userSelect.disabled = users.length === 0;
  }

  function formatMoney(value, currency) {
    if (value === undefined || value === null || value === '') return '—';
    if (typeof value === 'number' && Number.isFinite(value)) {
      return `${new Intl.NumberFormat('ar-IQ', { maximumFractionDigits: 2 }).format(value)}${currency ? ` ${currency}` : ''}`;
    }
    return `${String(value)}${currency && !String(value).includes(currency) ? ` ${currency}` : ''}`;
  }

  function formatMinor(value, currency) {
    if (value === undefined || value === null || value === '') return '—';
    // M1 only exposes IQD mock drafts. The server uses integer minor units.
    return formatMoney(value, currency);
  }
  function renderAccount(payload) {
    const account = payload.account || payload.wallet || payload.user || {};
    const balanceInfo = payload.balance && typeof payload.balance === 'object' ? payload.balance : null;
    const balance = balanceInfo ? balanceInfo.available_minor : (account.available_balance ?? account.balance ?? payload.available_balance ?? payload.balance);
    const currency = (balanceInfo && balanceInfo.currency) || account.currency || payload.currency || 'IQD';
    if (balance === undefined || balance === null) {
      dom.accountSummary.hidden = true;
      return;
    }
    dom.accountSummary.hidden = false;
    // The backend owns money formatting and minor-unit rules. Its display value wins.
    dom.balanceValue.textContent = (balanceInfo && balanceInfo.formatted) || formatMoney(balance, currency);
    dom.balanceCaption.textContent = text(account.label || account.name || payload.balance_label, 'الرصيد المتاح — بيانات محاكاة');
  }

  function updateEnvironment(payload) {
    const mode = String(payload.mode || payload.environment || payload.demo_mode || 'OFFLINE_DEMO').toUpperCase();
    const isMock = mode.includes('OFFLINE') || mode.includes('DEMO') || mode.includes('MOCK');
    dom.environmentLabel.textContent = isMock ? 'وضع تجريبي آمن' : 'حالة الخدمة المحلية';
    dom.environmentDetail.textContent = isMock
      ? 'بيانات وخدمات محاكاة فقط. لا توجد أي دفعات حقيقية أو خصم أو إشعار أو تنفيذ تلقائي للمواعيد.'
      : text(payload.environment_detail || payload.mode_description, 'هذه الواجهة تتصل بالخدمة المحلية فقط.');
  }

  function setActive(node) {
    dom.activeArea.replaceChildren();
    if (node) dom.activeArea.append(node);
  }

  function clearActiveDraft() {
    state.activeDraft = null;
    dom.activeArea.replaceChildren();
  }

  function isScheduledDraft(draft) {
    if (!draft || typeof draft !== 'object') return false;
    if (draft._lifecycle === 'schedule') return true;
    const kind = String(draft.kind || draft.type || draft.draft_type || '').toUpperCase();
    const review = draft.review || draft.summary || draft.details || {};
    return kind.includes('SCHEDULE')
      || review.authorization_mode === 'REMIND_AND_PREPARE'
      || review.execution_mode === 'FRESH_PAYMENT_DRAFT_REQUIRED';
  }

  function isPendingDraft(draft) {
    if (!draft || !draft.id) return false;
    const finalStates = ['SUCCEEDED', 'SUCCESS', 'COMPLETED', 'PAID', 'FAILED', 'CANCELLED', 'EXPIRED', 'DECLINED', 'CONFIGURED', 'ACTIVE_MOCK_ONLY', 'SCHEDULED_MOCK_ONLY'];
    return !finalStates.includes(String(draft.state || '').toUpperCase());
  }

  function appendResumeReviewControl(container) {
    const draft = state.activeDraft;
    if (!isPendingDraft(draft)) return;
    const scheduled = isScheduledDraft(draft);
    const noun = scheduled ? 'موعد تجريبي' : 'عملية';
    const resume = element('section', { className: 'draft-resume', attrs: { 'aria-label': `استئناف مراجعة ${noun}` } });
    const copy = element('p', { text: scheduled
      ? 'لديك إعداد موعد تجريبي بانتظار المراجعة. لا خصم ولا تنفيذ تلقائي.'
      : 'لديك عملية بانتظار المراجعة. لن تُنفّذ إلا بعد تأكيدها النهائي.' });
    const button = element('button', { className: 'secondary-button', text: `استئناف مراجعة ${noun}`, attrs: { type: 'button' } });
    button.addEventListener('click', () => recoverDraftStatus(draft));
    resume.append(copy, button);
    container.append(resume);
  }

  function extractDraft(payload) {
    const scheduleDraft = payload && payload.schedule_draft;
    const draft = scheduleDraft || (payload && (payload.draft || payload.transaction_draft || payload.review || (payload.type === 'draft' ? payload : null)));
    if (!draft || typeof draft !== 'object') return null;
    const id = draft.id || draft.draft_id || draft.draftId;
    return id ? { ...draft, id, ...(scheduleDraft ? { _lifecycle: 'schedule' } : {}) } : null;
  }

  function formatReviewValue(key, value) {
    const raw = String(value);
    const normalizedKey = String(key).toLowerCase();
    const localized = {
      MONTHLY: 'شهريًا',
      REMIND_AND_PREPARE: 'تذكير وتجهيز فقط',
      FRESH_PAYMENT_DRAFT_REQUIRED: 'مسودة دفع جديدة مطلوبة',
      MANUAL_MOCK_ONLY: 'تجريبي يدوي فقط',
      ACTIVE_MOCK_ONLY: 'نشط تجريبيًا فقط',
    };
    if (localized[raw]) return localized[raw];
    if ((normalizedKey === 'scheduled_for' || normalizedKey === 'next_occurrence') && !Number.isNaN(Date.parse(raw))) {
      return new Intl.DateTimeFormat('ar-IQ', {
        year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short', timeZone: 'Asia/Baghdad',
      }).format(new Date(raw));
    }
    return raw;
  }

  function detailsFromDraft(draft) {
    const source = draft.review || draft.summary || draft.details || draft;
    const currency = source.currency || draft.currency || 'IQD';
    const amount = source.amount_display || source.amount_formatted || (source.amount_minor !== undefined ? formatMinor(source.amount_minor, currency) : (source.amount !== undefined ? formatMoney(source.amount, currency) : null));
    const fee = source.fee_display || source.fee_formatted || (source.fee_minor !== undefined ? formatMinor(source.fee_minor, currency) : (source.fee !== undefined ? formatMoney(source.fee, currency) : null));
    const total = source.total_display || source.total_debit_display || source.total_debit_formatted || (source.total_debit_minor !== undefined ? formatMinor(source.total_debit_minor, currency) : (source.total_debit !== undefined ? formatMoney(source.total_debit, currency) : null));
    const fields = [
      ['operation', source.operation || source.operation_label || source.type || draft.operation || draft.kind || draft.type],
      ['recipient', source.recipient || source.recipient_name || source.recipient_or_biller || source.biller || source.biller_name],
      ['provider', source.provider || source.wallet_provider || source.biller_provider],
      ['account_identifier', source.account_display || source.account_identifier || source.account || source.reference],
      ['scheduled_for', source.scheduled_for || draft.scheduled_for],
      ['timezone', source.timezone || source.time_zone || draft.timezone],
      ['recurrence', source.recurrence || draft.recurrence],
      ['authorization_mode', source.authorization_mode || draft.authorization_mode],
      ['execution_mode', source.execution_mode || draft.execution_mode],
      ['amount', amount],
      ['fee', fee],
      ['total_debit', total],
      ['funding_source', source.funding_source || source.source_account],
      ['quote_expires_at', source.quote_expiry || source.quote_expires_at || source.expires_at || draft.expires_at],
    ];
    const extraFields = source.display_fields || source.fields;
    if (Array.isArray(extraFields)) {
      extraFields.forEach((field) => fields.push([field.key || field.label, field.value]));
    }
    const seen = new Set();
    return fields
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .filter(([key]) => {
        const normalizedKey = String(key);
        if (seen.has(normalizedKey)) return false;
        seen.add(normalizedKey);
        return true;
      })
      .map(([key, value]) => [key, formatReviewValue(key, value)]);
  }

  function isLtrValue(key, value) {
    const normalizedKey = String(key).toLowerCase();
    if (normalizedKey === 'scheduled_for' || normalizedKey === 'next_occurrence') return false;
    return /amount|fee|total|account|reference|id|expiry|expires|date|time|currency|timezone/i.test(normalizedKey)
      || /^[\d\s+\-.:/A-Z]+$/i.test(String(value));
  }

  function sourceWarnings(draft) {
    const source = draft.review || draft.summary || draft.details || draft;
    return source.warnings || source.warning || source.risk_warning || source.notice || draft.warning || draft.risk_warning || draft.notice;
  }

  function renderDraft(draft) {
    state.activeDraft = draft;
    setJourney('review');
    const scheduled = isScheduledDraft(draft);
    const card = element('section', { className: 'draft-card', attrs: { 'aria-labelledby': 'draft-title', 'data-draft-id': draft.id } });
    const header = element('div', { className: 'draft-header' });
    const heading = element('div');
    heading.append(
      element('h3', { text: scheduled ? 'راجع جدولة التحويل قبل التأكيد' : 'راجع العملية قبل التأكيد', attrs: { id: 'draft-title' } }),
      element('p', { text: scheduled
        ? 'هذه مراجعة لخيار تجريبي فقط؛ لا يوجد خصم أو تنفيذ آلي.'
        : 'هذه مراجعة مرتبطة بالعملية الحالية فقط.' }),
    );
    const stateLabel = draft.state === 'AWAITING_CONFIRMATION' ? 'بانتظار التأكيد' : text(draft.state, 'بانتظار التأكيد');
    header.append(heading, element('span', { className: 'draft-state', text: stateLabel }));
    card.append(header);

    const list = element('dl', { className: 'draft-details' });
    detailsFromDraft(draft).forEach(([key, value]) => {
      const row = element('div', { className: 'detail-row' });
      const label = LABELS[key] || String(key).replace(/_/g, ' ');
      const valueNode = element('dd', { text: value });
      if (isLtrValue(key, value)) valueNode.setAttribute('data-ltr', 'true');
      row.append(element('dt', { text: label }), valueNode);
      list.append(row);
    });
    card.append(list);

    const warningValue = sourceWarnings(draft);
    const warningText = Array.isArray(warningValue) ? warningValue.join(' · ') : warningValue;
    if (warningText) card.append(element('p', { className: 'draft-warning', text: warningText }));
    const context = draft.payment_context;
    if (draft.context_unavailable) card.append(element('p', { className: 'draft-warning', text: 'تفاصيل التنبيه الإضافية غير متاحة حالياً. بيانات المراجعة الأساسية جاية من المحفظة؛ تحقق من الاسم والمبلغ بنفسك.' }));
    if (context && !scheduled) {
      const remaining = element('section', { className: 'remaining-balance', attrs: { 'aria-label': 'الرصيد بعد العملية' } });
      remaining.append(element('span', { text: 'الرصيد المتوقع بعد المبلغ والرسوم' }), element('strong', { text: formatMoney(context.estimated_after_minor, 'IQD'), attrs: { 'data-ltr': 'true' } }), element('small', { text: context.balance_note }));
      card.append(remaining);
      asArray(context.signals).forEach((signal) => {
        const coaching = element('aside', { className: 'risk-coaching', attrs: { role: 'note' } });
        coaching.append(element('strong', { text: signal.title }), element('p', { text: signal.explanation }));
        card.append(coaching);
      });
      if (asArray(context.signals).length) card.append(element('p', { className: 'risk-choice', text: 'هذا تنبيه للمراجعة. تگدر تلغي، أو تتابع بالتأكيد بعد ما تتحقق بنفسك.' }));
    }
    if (scheduled) {
      card.append(element('p', {
        className: 'mock-schedule-notice',
        text: 'هذا الإعداد التجريبي لا ينشئ دفعة ولا يخصم رصيدًا، ولا يشغّل مؤقّتًا أو يرسل إشعارات. عند أي دفع مستقبلي يلزم إنشاء مسودة دفع جديدة ومراجعتها.',
      }));
    }

    const controls = element('div', { className: 'draft-actions' });
    const confirmLabel = scheduled ? 'تأكيد حفظ إعداد الموعد التجريبي' : `تأكيد خصم ${formatMoney((draft.review || {}).total_debit_minor, 'IQD')} تجريبياً`;
    const confirm = element('button', { className: 'primary-button', text: draft.can_confirm === false ? 'المراجعة غير جاهزة للتأكيد' : confirmLabel, attrs: { type: 'button', 'data-confirm-draft': draft.id } });
    if (draft.can_confirm === false) confirm.disabled = true;
    const cancel = element('button', { className: 'secondary-button', text: 'إلغاء المراجعة', attrs: { type: 'button', 'data-cancel-draft': draft.id } });
    confirm.addEventListener('click', () => confirmDraft(draft, confirm, cancel));
    cancel.addEventListener('click', () => cancelDraft(draft, confirm, cancel));
    controls.append(confirm, cancel, element('p', { className: 'confirm-guard', text: scheduled
      ? 'هذا الزر يحفظ إعداد الموعد التجريبي فقط. لا توجد دفعة أو خصم أو تنفيذ آلي.'
      : 'لن تنفّذ العملية إلا بعد ضغط هذا الزر. الرد النصي في المحادثة لا يؤكدها.' }));
    card.append(controls);
    setActive(card);
    window.requestAnimationFrame(() => confirm.focus());
  }

  function scheduleFormFromPayload(payload) {
    const candidates = [payload && payload.schedule_transfer_form, payload && payload.view, payload && payload.data];
    for (const candidate of candidates) {
      if (!candidate || typeof candidate !== 'object') continue;
      if (String(candidate.kind || '').toLowerCase() !== 'scheduled_transfer_form') continue;
      return candidate.data && typeof candidate.data === 'object' ? candidate.data : candidate;
    }
    return null;
  }

  function normalizeScheduleFormConfig(config) {
    const raw = config && typeof config === 'object' ? config : {};
    const recipients = asArray(raw.recipients).map((recipient) => {
      if (!recipient || typeof recipient !== 'object' || typeof recipient.id !== 'string' || !recipient.id) return null;
      return {
        id: recipient.id,
        label: text(recipient.label || recipient.display_name_ar || recipient.name, recipient.id),
        provider: text(recipient.provider, ''),
        account: text(recipient.account_identifier || recipient.account, ''),
      };
    }).filter(Boolean);
    const allowedDays = raw.allowed_day_of_month || raw.allowedDayOfMonth || {};
    const dayMinimum = Number.isInteger(allowedDays.minimum) ? allowedDays.minimum : 1;
    const dayMaximum = Number.isInteger(allowedDays.maximum) ? allowedDays.maximum : 28;
    return {
      recipients,
      recurrence: 'MONTHLY',
      timezone: (raw.timezone || raw.timeZone) === 'Asia/Baghdad' ? (raw.timezone || raw.timeZone) : 'Asia/Baghdad',
      authorizationMode: raw.authorization_mode || raw.authorizationMode || 'REMIND_AND_PREPARE',
      executionMode: raw.execution_mode || raw.executionMode || 'FRESH_PAYMENT_DRAFT_REQUIRED',
      minimumScheduledFor: raw.minimum_scheduled_for || raw.minimumScheduledFor || '',
      dayMinimum,
      dayMaximum,
      values: raw.values && typeof raw.values === 'object' ? raw.values : {},
      errorMessage: raw.errorMessage || '',
    };
  }

  function rememberScheduleForm(payload) {
    const form = scheduleFormFromPayload(payload);
    if (!form) return null;
    state.scheduleFormConfig = normalizeScheduleFormConfig(form);
    return state.scheduleFormConfig;
  }

  function scheduleActionFrom(payload) {
    const candidates = [payload && payload.action, ...asArray(responseActions(payload)), ...state.actions.map((action) => action.raw || action)];
    for (const candidate of candidates) {
      const action = normalizeAction(candidate || {});
      if (String(action.id).toUpperCase() === 'OPEN_SCHEDULED_TRANSFER') return action;
    }
    return null;
  }

  function toLocalDateTimeValue(value) {
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) return '';
    const local = new Date(date.getTime() - (date.getTimezoneOffset() * 60_000));
    return local.toISOString().slice(0, 16);
  }

  function defaultScheduledDateTime(config) {
    const minimumDate = config.minimumScheduledFor ? new Date(config.minimumScheduledFor) : new Date(Date.now() + (24 * 60 * 60 * 1000));
    const candidate = Number.isNaN(minimumDate.getTime()) ? new Date(Date.now() + (24 * 60 * 60 * 1000)) : minimumDate;
    candidate.setMinutes(0, 0, 0);
    if (candidate.getDate() > config.dayMaximum) {
      return toLocalDateTimeValue(new Date(candidate.getFullYear(), candidate.getMonth() + 1, config.dayMinimum, 9, 0, 0).toISOString());
    }
    if (candidate.getDate() < config.dayMinimum) candidate.setDate(config.dayMinimum);
    return toLocalDateTimeValue(candidate.toISOString());
  }

  function renderScheduledTransferForm(action, suppliedConfig) {
    const config = normalizeScheduleFormConfig(suppliedConfig || state.scheduleFormConfig || {});
    state.scheduleFormConfig = config;
    const card = element('section', { className: 'data-card schedule-form-card', attrs: { 'aria-labelledby': 'schedule-form-title' } });
    card.append(
      element('h3', { text: 'جدولة تحويل تجريبي', attrs: { id: 'schedule-form-title' } }),
      element('p', { text: 'اختر تفاصيل صريحة للموعد الشهري، ثم اعرض مراجعة الخادم قبل حفظ الإعداد.' }),
    );

    const notice = element('aside', { className: 'mock-schedule-notice', attrs: { role: 'note', 'aria-label': 'حدود الجدولة التجريبية' } });
    notice.append(
      element('strong', { text: 'محاكاة فقط: ' }),
      document.createTextNode('لن تُخصم أموال، ولن يبدأ مؤقّت أو إشعار أو تنفيذ تلقائي. أي دفعة لاحقة تحتاج مسودة دفع جديدة ومراجعة صريحة.'),
    );
    card.append(notice);

    if (config.errorMessage) card.append(element('p', { className: 'inline-form-error', text: config.errorMessage, attrs: { role: 'alert' } }));

    const form = element('form', { className: 'scheduled-transfer-form', attrs: { novalidate: '' } });
    const recipientField = element('div', { className: 'form-field' });
    const recipientLabel = element('label', { text: 'المستفيد التجريبي المحفوظ', attrs: { for: 'schedule-recipient' } });
    const recipientHelp = element('p', { className: 'field-help', text: 'تظهر جهات هذا الحساب التجريبي فقط.', attrs: { id: 'schedule-recipient-help' } });
    const recipientSelect = element('select', { attrs: { id: 'schedule-recipient', name: 'recipient_id', required: '', 'aria-describedby': 'schedule-recipient-help' } });
    recipientSelect.append(element('option', { text: 'اختر المستفيد التجريبي', attrs: { value: '' } }));
    config.recipients.forEach((recipient) => {
      const suffix = [recipient.provider, recipient.account].filter(Boolean).join(' · ');
      const option = element('option', { text: suffix ? `${recipient.label} — ${suffix}` : recipient.label, attrs: { value: recipient.id } });
      option.selected = recipient.id === config.values.recipient_id;
      recipientSelect.append(option);
    });
    recipientField.append(recipientLabel, recipientSelect, recipientHelp);
    form.append(recipientField);

    const amountField = element('div', { className: 'form-field' });
    const amountLabel = element('label', { text: 'المبلغ بالدينار العراقي', attrs: { for: 'schedule-amount' } });
    const amountHelp = element('p', { className: 'field-help', text: 'أدخل مبلغًا صحيحًا. لن يُخصم الآن أو تلقائيًا.', attrs: { id: 'schedule-amount-help' } });
    const amountInput = element('input', { attrs: {
      id: 'schedule-amount', name: 'amount_minor', type: 'number', inputmode: 'numeric', min: '1000', max: '1000000', step: '1000', required: '', autocomplete: 'off', dir: 'ltr', 'aria-describedby': 'schedule-amount-help', placeholder: '50000',
    } });
    if (config.values.amount_minor !== undefined) amountInput.value = String(config.values.amount_minor);
    amountField.append(amountLabel, amountInput, amountHelp);
    form.append(amountField);

    const timeField = element('div', { className: 'form-field' });
    const timeLabel = element('label', { text: 'موعد التذكير والتحضير', attrs: { for: 'schedule-datetime' } });
    const timeHelp = element('p', { className: 'field-help', text: `وقت صريح ضمن ${config.timezone}. في هذا الإصدار الشهري اختر يومًا من ${config.dayMinimum} إلى ${config.dayMaximum}؛ سيعرضه الخادم في المراجعة قبل أي حفظ.`, attrs: { id: 'schedule-datetime-help' } });
    const timeInput = element('input', { attrs: {
      id: 'schedule-datetime', name: 'scheduled_for', type: 'datetime-local', required: '', min: defaultScheduledDateTime(config), 'aria-describedby': 'schedule-datetime-help',
    } });
    timeInput.value = toLocalDateTimeValue(config.values.scheduled_for) || defaultScheduledDateTime(config);
    timeField.append(timeLabel, timeInput, timeHelp);
    form.append(timeField);

    const guard = element('dl', { className: 'schedule-guard-list', attrs: { 'aria-label': 'قيود إعداد الموعد' } });
    const guardItems = [
      ['التكرار', 'شهريًا فقط'],
      ['المنطقة الزمنية', config.timezone],
      ['نمط الصلاحية', formatReviewValue('authorization_mode', config.authorizationMode)],
      ['آلية التنفيذ', formatReviewValue('execution_mode', config.executionMode)],
    ];
    guardItems.forEach(([label, value]) => {
      const row = element('div');
      const valueNode = element('dd', { text: value });
      if (isLtrValue(label === 'المنطقة الزمنية' ? 'timezone' : '', value)) valueNode.setAttribute('data-ltr', 'true');
      row.append(element('dt', { text: label }), valueNode);
      guard.append(row);
    });
    form.append(guard);

    const submit = element('button', { className: 'primary-button', text: 'اعرض مراجعة الجدولة', attrs: { type: 'submit' } });
    submit.disabled = !config.recipients.length || !action || !action.id;
    form.append(submit);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (state.busy || !action || !action.id) return;
      const recipientId = recipientSelect.value;
      const amountMinor = Number(amountInput.value);
      const selectedDate = new Date(timeInput.value);
      const minimumDate = config.minimumScheduledFor ? new Date(config.minimumScheduledFor) : null;
      if (!recipientId) {
        recipientSelect.setCustomValidity('اختر مستفيدًا تجريبيًا محفوظًا أولًا.');
        recipientSelect.reportValidity();
        return;
      }
      recipientSelect.setCustomValidity('');
      if (!Number.isSafeInteger(amountMinor) || amountMinor < 1000) {
        amountInput.setCustomValidity('أدخل مبلغًا صحيحًا لا يقل عن ١٬٠٠٠ دينار.');
        amountInput.reportValidity();
        return;
      }
      amountInput.setCustomValidity('');
      if (Number.isNaN(selectedDate.getTime()) || (minimumDate && !Number.isNaN(minimumDate.getTime()) && selectedDate.getTime() < minimumDate.getTime())) {
        timeInput.setCustomValidity('اختر موعدًا صريحًا لا يسبق الحد الأدنى المعروض.');
        timeInput.reportValidity();
        return;
      }
      const dayOfMonth = Number(timeInput.value.slice(8, 10));
      if (!Number.isInteger(dayOfMonth) || dayOfMonth < config.dayMinimum || dayOfMonth > config.dayMaximum) {
        timeInput.setCustomValidity(`للتكرار الشهري في هذا الإصدار، اختر يومًا من ${config.dayMinimum} إلى ${config.dayMaximum}.`);
        timeInput.reportValidity();
        return;
      }
      timeInput.setCustomValidity('');
      const retryConfig = {
        ...config,
        values: { recipient_id: recipientId, amount_minor: amountMinor, scheduled_for: selectedDate.toISOString() },
      };
      submit.disabled = true;
      setBusy(true, 'جارِ إنشاء مراجعة الموعد…');
      renderLoading('جارِ إنشاء مراجعة إعداد الموعد التجريبي فقط…');
      try {
        const response = await api.action(action.id, {
          recipient_id: recipientId,
          amount_minor: amountMinor,
          currency: 'IQD',
          scheduled_for: selectedDate.toISOString(),
          timezone: config.timezone,
          recurrence: 'MONTHLY',
        });
        processResponse(response);
      } catch (error) {
        renderScheduledTransferForm(action, { ...retryConfig, errorMessage: text(error.message, 'تعذر إنشاء مراجعة الموعد التجريبي.') });
        showToast('لم يُحفظ أي موعد. راجع الحقول وحاول مرة أخرى.', 'error');
      } finally {
        setBusy(false);
      }
    });
    card.append(form);
    if (!config.recipients.length) {
      card.append(element('p', { className: 'inline-form-error', text: 'لا توجد جهات تجريبية محفوظة متاحة لهذه الجلسة؛ لم نرسل أي طلب.' }));
    }
    appendResumeReviewControl(card);
    setActive(card);
    window.requestAnimationFrame(() => (config.recipients.length ? recipientSelect : form).focus());
  }

  function extractSchedule(payload) {
    const schedule = payload && payload.schedule;
    if (!schedule || typeof schedule !== 'object') return null;
    const id = schedule.id || schedule.schedule_id || schedule.plan_id;
    return id ? { ...schedule, id } : null;
  }

  function renderScheduleConfiguration(payload) {
    const schedule = extractSchedule(payload);
    if (!schedule) return false;
    const draft = extractDraft(payload) || {};
    const review = draft.review || {};
    const card = element('section', { className: 'schedule-card', attrs: { tabindex: '-1', 'aria-live': 'polite' } });
    const header = element('div', { className: 'schedule-card-header' });
    const headerCopy = element('div');
    headerCopy.append(
      element('h3', { text: 'تم حفظ إعداد الموعد التجريبي' }),
      element('p', { text: 'إعداد فقط — ليس تحويلًا ولا دفعة.' }),
    );
    header.append(headerCopy, element('span', { className: 'draft-state', text: 'محاكاة فقط' }));
    card.append(header);
    const body = element('div', { className: 'schedule-card-body' });
    body.append(element('p', { text: 'لم يُنشأ دفع ولم يُخصم أي رصيد. لا يوجد مؤقّت أو إشعار أو تنفيذ تلقائي؛ أي دفع لاحق يحتاج مسودة دفع جديدة ومراجعة صريحة.' }));
    const fields = [
      ['schedule_id', schedule.id],
      ['status', schedule.status || 'ACTIVE_MOCK_ONLY'],
      ['scheduled_for', schedule.scheduled_for || review.scheduled_for],
      ['timezone', schedule.timezone || review.timezone],
      ['recurrence', schedule.recurrence || review.recurrence || 'MONTHLY'],
      ['authorization_mode', schedule.authorization_mode || review.authorization_mode || 'REMIND_AND_PREPARE'],
      ['execution_mode', schedule.execution_mode || review.execution_mode || 'FRESH_PAYMENT_DRAFT_REQUIRED'],
      ['debit_minor', schedule.debit_minor],
    ].filter(([, value]) => value !== undefined && value !== null && value !== '');
    const list = element('dl', { className: 'data-list' });
    fields.forEach(([key, value]) => {
      const row = element('div', { className: 'data-row' });
      const rendered = formatReviewValue(key, value);
      const valueNode = element('dd', { text: rendered });
      if (isLtrValue(key, rendered)) valueNode.setAttribute('data-ltr', 'true');
      row.append(element('dt', { text: LABELS[key] || String(key).replace(/_/g, ' ') }), valueNode);
      list.append(row);
    });
    body.append(list);
    card.append(body);
    setActive(card);
    window.requestAnimationFrame(() => card.focus());
    return true;
  }
  function renderQrCode(matrix) {
    if (
      !Array.isArray(matrix) ||
      matrix.length !== 25 ||
      matrix.some((row) => !Array.isArray(row) || row.length !== 25 || row.some((cell) => cell !== 0 && cell !== 1))
    ) return null;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 33 33');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'رمز استلام تجريبي غير قابل للدفع');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('shape-rendering', 'crispEdges');
    const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    background.setAttribute('width', '33');
    background.setAttribute('height', '33');
    background.setAttribute('fill', '#ffffff');
    svg.append(background);
    let pathData = '';
    matrix.forEach((row, rowIndex) => row.forEach((cell, columnIndex) => {
      if (cell === 1) pathData += `M${columnIndex + 4} ${rowIndex + 4}h1v1h-1z`;
    }));
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', pathData);
    path.setAttribute('fill', '#211c2a');
    svg.append(path);
    const figure = element('figure', { className: 'qr-code' });
    figure.append(svg, element('figcaption', { text: 'رمز تجريبي فقط • غير قابل للدفع' }));
    return figure;
  }

  function renderDataCard(payload) {
    const view = payload.view || (payload.data && payload.data.kind ? payload.data : null);
    const data = (view && view.data) || view || payload.data || payload.result || payload;
    const kind = (view && view.kind) || data.kind || payload.kind || '';
    const titles = {
      receive_qr: 'رمز الاستلام',
      history: 'سجل العمليات',
      schedules: 'المواعيد',
      balance: 'رصيد المحفظة التجريبية',
    };
    const card = element('section', { className: 'data-card', attrs: { 'aria-label': 'نتيجة للعرض' } });
    const title = data.title || payload.title || payload.view_title || titles[kind] || 'نتيجة الطلب';
    const message = data.message || data.disclaimer || payload.message || payload.reply || payload.text;
    card.append(element('h3', { text: title }));
    if (message) card.append(element('p', { text: message }));
    if (kind === 'balance') card.append(element('p', { className: 'balance-value', text: data.formatted || formatMoney(data.available_minor, 'IQD'), attrs: { 'data-ltr': 'true' } }));
    if (kind === 'receive_qr' && data.matrix) {
      const qrFigure = renderQrCode(data.matrix);
      if (qrFigure) card.append(qrFigure);
    }

    const entries = data.items || data.rows || data.fields || data.details;
    if (Array.isArray(entries) && entries.length) {
      const list = element('dl', { className: 'data-list' });
      entries.forEach((entry, index) => {
        const item = typeof entry === 'object' && entry !== null ? entry : { label: `بند ${index + 1}`, value: entry };
        const label = item.label || item.name || item.key || item.recipient || item.counterparty || `بند ${index + 1}`;
        const value = item.value ?? item.display_value ?? item.formatted ?? (item.amount_minor !== undefined ? formatMoney(item.amount_minor, item.currency || 'IQD') : undefined) ?? item.amount ?? item.text ?? item.reference ?? '';
        const row = element('div', { className: 'data-row' });
        const dd = element('dd', { text: value });
        if (isLtrValue(label, value)) dd.setAttribute('data-ltr', 'true');
        row.append(element('dt', { text: label }), dd);
        if (kind === 'history') {
          const detail = element('div', { className: 'history-detail' });
          const statusLabel = { SUCCEEDED: 'ناجحة', FAILED: 'فاشلة', UNKNOWN: 'غير مؤكدة' }[item.status] || item.status;
          detail.append(element('small', { text: `${statusLabel || ''} · ${item.reference || ''}` }));
          const lookup = element('button', { className: 'text-button', text: 'الحالة والمساعدة', attrs: { type: 'button' } });
          lookup.addEventListener('click', () => recoverStatus(item.id, lookup));
          detail.append(lookup);
          row.append(detail);
        }
        list.append(row);
      });
      card.append(list);
    } else if (data.payload || data.qr_payload || payload.qr_payload) {
      const code = data.payload || data.qr_payload || payload.qr_payload;
      const list = element('dl', { className: 'data-list' });
      const row = element('div', { className: 'data-row' });
      const codeNode = element('dd', { text: code, attrs: { 'data-ltr': 'true' } });
      row.append(element('dt', { text: data.label || 'رمز الاستلام' }), codeNode);
      list.append(row);
      card.append(list);
    }
    if (data.payable === false) {
      card.append(element('p', { className: 'draft-warning', text: 'هذا رمز استلام تجريبي وغير قابل للدفع.' }));
    }
    if (data.next_step) card.append(element('p', { className: 'next-step', text: data.next_step }));
    if (kind === 'wallet_insights') {
      const evidence = element('details', { className: 'source-evidence' });
      evidence.append(element('summary', { text: 'مصادر الأرقام وحدودها' }), element('p', { text: 'آخر ١٠٠ سجل تجريبي فقط. هذا مو ربح أو توقع دخل، والرصيد الحالي مستقل عن أمثلة السجل القديمة.' }));
      asArray(data.source_records).forEach((record) => evidence.append(element('p', { text: `${record.reference} · ${record.counterparty} · ${formatMoney(record.amount_minor, 'IQD')} · ${record.status}` })));
      card.append(evidence);
    }
    if (kind === 'support_draft') {
      const draftText = element('textarea', { className: 'support-copy', attrs: { readonly: '', rows: '9', 'aria-label': 'نص مسودة الدعم' } });
      draftText.value = data.draft_text || '';
      const copy = element('button', { className: 'secondary-button', text: 'نسخ المسودة للمراجعة', attrs: { type: 'button' } });
      copy.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(draftText.value); showToast('تم نسخ المسودة. ما انرسلت لأي جهة.'); }
        catch (_) { draftText.focus(); draftText.select(); showToast('حددنا النص حتى تنسخه بنفسك.'); }
      });
      card.append(draftText, copy);
    }
    return card;
  }
  function normalizeStatus(payload) {
    const source = payload.transaction || payload.status || payload.result || payload;
    const raw = String(source.status || payload.status || payload.outcome || '').toUpperCase();
    const transactionId = source.transaction_id || source.id || payload.transaction_id || payload.id;
    return {
      raw,
      transactionId,
      reference: source.reference || source.receipt_reference || payload.reference || payload.receipt_reference,
      message: source.message || source.recovery_message || payload.message || payload.reply || '',
      receipt: source.receipt || payload.receipt,
      source,
    };
  }

  function renderStatus(payload) {
    setJourney('result');
    const status = normalizeStatus(payload);
    const isUnknown = ['UNKNOWN', 'PENDING', 'SUBMITTED', 'PROCESSING'].includes(status.raw);
    const isFailed = ['FAILED', 'CANCELLED', 'EXPIRED', 'DECLINED'].includes(status.raw);
    const isSuccess = ['SUCCEEDED', 'SUCCESS', 'COMPLETED', 'PAID'].includes(status.raw) || Boolean(status.receipt);
    const card = element('section', { className: `${isSuccess ? 'receipt-card' : 'status-card'}${isUnknown ? ' is-unknown' : ''}${isFailed ? ' is-failed' : ''}`, attrs: { 'aria-live': 'polite' } });
    const header = element('div', { className: isSuccess ? 'receipt-header' : 'status-card-header' });
    const content = element('div');
    const heading = isSuccess ? 'تم تسجيل العملية التجريبية' : isUnknown ? 'الحالة غير مؤكدة بعد' : isFailed ? 'لم تكتمل العملية' : 'حالة العملية';
    const description = isSuccess
      ? 'هذه إيصال من خدمة المحفظة المحاكاة.'
      : isUnknown
        ? 'لا تعِد إنشاء الدفع. افحص العملية الأصلية من الزر أدناه.'
        : 'راجع تفاصيل الحالة قبل اتخاذ أي خطوة أخرى.';
    content.append(element('h3', { text: heading }), element('p', { text: description }));
    header.append(content, element('span', { className: 'draft-state', text: text(status.raw || 'STATUS') }));
    card.append(header);
    const body = element('div', { className: isSuccess ? 'receipt-body' : 'status-card-body' });
    body.append(element('p', { text: text(status.message, isSuccess ? 'اكتملت المعالجة ضمن بيئة العرض.' : 'لم يقدم الخادم تفاصيل إضافية.') }));
    if (status.reference || status.transactionId) {
      body.append(element('span', { className: 'receipt-reference', text: `المرجع: ${status.reference || status.transactionId}` }));
    }
    if (isUnknown && status.transactionId) {
      const controls = element('div', { className: 'recovery-actions' });
      const refresh = element('button', { className: 'secondary-button', text: 'تحقق من حالة العملية', attrs: { type: 'button' } });
      refresh.addEventListener('click', () => recoverStatus(status.transactionId, refresh));
      controls.append(refresh);
      body.append(controls);
    }
    if (status.transactionId) {
      const help = element('button', { className: 'secondary-button support-trigger', text: 'تحتاج مساعدة؟ جهز مسودة دعم', attrs: { type: 'button' } });
      help.addEventListener('click', () => renderSupportForm(status.reference || status.transactionId));
      body.append(help);
    }
    appendResumeReviewControl(body);
    card.append(body);
    setActive(card);
  }

  function renderError(message, options) {
    const card = element('section', { className: 'error-card', attrs: { role: 'alert' } });
    card.append(element('h3', { text: (options && options.title) || 'تعذر إكمال الطلب' }), element('p', { text: message }));
    if (options && options.retry) {
      const actions = element('div', { className: 'recovery-actions' });
      const retry = element('button', { className: 'secondary-button', text: 'حاول مرة ثانية', attrs: { type: 'button' } });
      retry.addEventListener('click', options.retry);
      actions.append(retry);
      card.append(actions);
    }
    appendResumeReviewControl(card);
    setActive(card);
  }

  function renderLoading(message) {
    const card = element('div', { className: 'loading-card', attrs: { role: 'status' } });
    card.append(element('span', { className: 'spinner', attrs: { 'aria-hidden': 'true' } }), element('span', { text: message || 'جارِ المعالجة…' }));
    setActive(card);
  }

  function responseMessage(payload) {
    return payload.message || payload.reply || payload.text || payload.assistant_message || payload.assistant?.message;
  }

  function responseActions(payload) {
    return payload.actions || payload.action_buttons || payload.assistant?.actions || [];
  }

  function processResponse(payload, options) {
    if (payload.advisory_recorded === false) appendMessage('system', 'نتيجة الإجراء محفوظة في المحفظة. تعذر حفظ سجل التنبيه الإضافي؛ لا تعيد الدفع بسبب هالتنبيه.');
    if (payload.agent) renderAgent(payload.agent);
    if (payload.balance) renderAccount(payload);
    if (payload.view && payload.view.kind === 'balance') renderAccount({ balance: payload.view.data });
    const suppressMessage = Boolean(options && options.suppressMessage);
    const messagesRendered = suppressMessage ? false : appendServerMessages(payload.messages);
    const message = responseMessage(payload);
    if (!suppressMessage && !messagesRendered && message) appendMessage('assistant', message, responseActions(payload));
    else if (!suppressMessage && !messagesRendered && asArray(responseActions(payload)).length) appendMessage('assistant', 'تفضل، هذه الخيارات المتاحة.', responseActions(payload));
    if (!suppressMessage && payload.clarification) appendClarification(payload.clarification, messagesRendered || Boolean(message));
    if (payload.view && payload.view.kind === 'support_form') { renderSupportForm(); return; }
    if (payload.view && payload.view.kind === 'payment_status') { renderStatus({ transaction: payload.view.data }); return; }

    const scheduleForm = rememberScheduleForm(payload);
    if (scheduleForm) {
      const scheduleAction = scheduleActionFrom(payload);
      if (scheduleAction) renderScheduledTransferForm(scheduleAction, scheduleForm);
      else renderError('تعذر العثور على الإجراء المسجل لجدولة التحويل؛ لم نرسل أي طلب.', { title: 'الخدمة غير متاحة' });
      return;
    }

    const status = normalizeStatus(payload);
    if (status.raw || status.receipt || payload.transaction || payload.receipt) {
      renderStatus(payload);
      return;
    }

    if (extractSchedule(payload)) {
      renderScheduleConfiguration(payload);
      return;
    }

    const draft = extractDraft(payload);
    if (draft) {
      renderDraft(draft);
      return;
    }

    if (payload.data || payload.view || payload.result || payload.qr_payload) {
      const viewCard = renderDataCard(payload);
      appendResumeReviewControl(viewCard);
      setActive(viewCard);
      return;
    }

    if (isPendingDraft(state.activeDraft)) {
      const savedReview = element('section', { className: 'data-card', attrs: { 'aria-label': 'مراجعة عملية محفوظة' } });
      savedReview.append(element('h3', { text: 'مراجعة العملية محفوظة' }), element('p', { text: 'يمكنك متابعة المحادثة أو العودة إلى مراجعة العملية في أي وقت.' }));
      appendResumeReviewControl(savedReview);
      setActive(savedReview);
    } else {
      setJourney('request');
      setActive(null);
    }
  }

  function renderSupportForm(reference) {
    const card = element('section', { className: 'data-card' });
    card.append(element('h3', { text: 'جهز طلب دعم من سجل العملية' }), element('p', { text: 'هاي مسودة تبقى للمراجعة عندك. ما نرسلها أو نفتح تذكرة خارجية.' }));
    const form = element('form', { className: 'status-lookup' });
    const ref = element('input', { attrs: { id: 'support-reference', required: '', maxlength: '100', dir: 'ltr', placeholder: 'MOCK-…' } });
    ref.value = reference || '';
    const issue = element('textarea', { attrs: { id: 'support-issue', required: '', maxlength: '500', rows: '3', placeholder: 'شنو المشكلة؟ بدون PIN أو OTP أو معلومات حقيقية.' } });
    const submit = element('button', { className: 'primary-button', text: 'عرض مسودة الدعم', attrs: { type: 'submit' } });
    form.append(element('label', { text: 'مرجع العملية أو معرّفها', attrs: { for: 'support-reference' } }), ref, element('label', { text: 'وصفك للمشكلة', attrs: { for: 'support-issue' } }), issue, submit);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (state.busy || !ref.value.trim() || !issue.value.trim()) return;
      setBusy(true, 'جارِ قراءة السجل وتجهيز المسودة…'); submit.disabled = true;
      try { processResponse(await api.action('PREPARE_SUPPORT_REQUEST', { transaction_id: ref.value.trim(), issue: issue.value.trim() })); }
      catch (error) { showToast(error.message, 'error'); }
      finally { setBusy(false); submit.disabled = false; }
    });
    card.append(form); appendResumeReviewControl(card); setActive(card);
  }
  function beginChatStarter(message) {
    if (state.busy || !state.bootstrapped) return;
    dom.input.value = message;
    dom.input.focus();
    if (dom.form.requestSubmit) dom.form.requestSubmit();
    else dom.form.dispatchEvent(new Event('submit', { cancelable: true }));
  }

  function renderStatusLookup(action) {
    const card = element('section', { className: 'data-card', attrs: { 'aria-labelledby': 'status-lookup-title' } });
    const title = element('h3', { text: 'تحقق من حالة عملية', attrs: { id: 'status-lookup-title' } });
    const help = element('p', { text: 'اكتب معرّف العملية أو المرجع. هذا الاستعلام للعرض فقط ولا ينشئ دفعة جديدة.', attrs: { id: 'status-lookup-help' } });
    const form = element('form', { className: 'status-lookup', attrs: { novalidate: '' } });
    const label = element('label', { text: 'معرّف العملية أو المرجع', attrs: { for: 'status-lookup-id' } });
    const input = element('input', {
      attrs: {
        id: 'status-lookup-id',
        name: 'transaction_id',
        type: 'text',
        inputmode: 'text',
        autocomplete: 'off',
        required: '',
        maxlength: '160',
        dir: 'ltr',
        'aria-describedby': 'status-lookup-help',
        placeholder: 'معرّف العملية أو المرجع',
      },
    });
    const submit = element('button', { className: 'primary-button', text: 'تحقق من الحالة', attrs: { type: 'submit' } });
    form.append(label, input, submit);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const transactionId = input.value.trim();
      if (!transactionId) {
        input.setCustomValidity('اكتب معرّف العملية أو المرجع أولًا.');
        input.reportValidity();
        return;
      }
      input.setCustomValidity('');
      if (state.busy) return;
      setBusy(true, 'جارِ التحقق من الحالة…');
      renderLoading('جارِ الاستعلام عن العملية الأصلية فقط…');
      try {
        const response = await api.action(action.id, { transaction_id: transactionId });
        processResponse(response);
      } catch (error) {
        renderError(text(error.message, 'تعذر التحقق من الحالة.'), { retry: () => renderStatusLookup(action) });
        showToast('لم نتمكن من قراءة الحالة؛ لم نرسل دفعة جديدة.', 'error');
      } finally {
        setBusy(false);
      }
    });
    card.append(title, help, form);
    appendResumeReviewControl(card);
    setActive(card);
    window.requestAnimationFrame(() => input.focus());
  }

  async function handleAction(action) {
    if (!action.enabled || !action.id || state.busy) return;
    const actionId = String(action.id).toUpperCase();
    if (actionId === 'OPEN_TRANSFER') {
      beginChatStarter('تحويل');
      return;
    }
    if (actionId === 'OPEN_BILL_PAYMENT') {
      beginChatStarter('فاتورة');
      return;
    }
    if (actionId === 'OPEN_SCHEDULED_TRANSFER') {
      if (state.scheduleFormConfig) renderScheduledTransferForm(action, state.scheduleFormConfig);
      else beginChatStarter('جدولة تحويل');
      return;
    }
    if (actionId === 'CHECK_PAYMENT_STATUS') {
      renderStatusLookup(action);
      return;
    }
    if (actionId === 'PREPARE_SUPPORT_REQUEST') { renderSupportForm(); return; }
    setBusy(true, 'جارِ فتح الخدمة المسجلة…');
    renderLoading(`جارِ فتح «${action.label}»…`);
    try {
      const response = await api.action(action.id);
      processResponse(response);
    } catch (error) {
      renderError(text(error.message, 'تعذر فتح الخدمة.'), { retry: () => handleAction(action) });
      showToast('لم تكتمل الخدمة. لم يتم تنفيذ أي دفع.', 'error');
    } finally {
      setBusy(false);
    }
  }
  async function submitChat(event) {
    event.preventDefault();
    const message = dom.input.value.trim();
    if (!message || state.busy) return;
    appendMessage('user', message);
    dom.input.value = '';
    dom.input.style.height = '';
    setBusy(true, 'جارِ قراءة طلبك…');
    renderLoading('جارِ معالجة الطلب ضمن الخدمة المحلية…');
    try {
      const response = await api.chat(message);
      processResponse(response);
    } catch (error) {
      appendMessage('system', 'تعذر إكمال الرد. ما أرسلنا تأكيد دفع. إذا عندك مراجعة سابقة، افحصها قبل المتابعة.', []);
      if (state.agent && state.agent.mode === 'LIVE_MODEL') renderAgent({ ...state.agent, last_request: 'failed', trace: [] });
      renderError(text(error.message), { retry: () => { dom.input.value = message; dom.input.focus(); } });
      showToast('فشل الاتصال بالخدمة المحلية.', 'error');
    } finally {
      setBusy(false);
      dom.input.focus();
    }
  }

  async function confirmDraft(draft, confirmButton, cancelButton) {
    if (state.busy || !state.activeDraft || state.activeDraft.id !== draft.id) return;
    const scheduled = isScheduledDraft(draft);
    confirmButton.disabled = true;
    cancelButton.disabled = true;
    setBusy(true, scheduled ? 'جارِ حفظ إعداد الموعد…' : 'جارِ إرسال التأكيد النهائي…');
    renderLoading(scheduled ? 'جارِ التحقق من إعداد الموعد التجريبي الحالي…' : 'جارِ التحقق من العملية الحالية… لا تغلق الصفحة.');
    try {
      const response = scheduled ? await api.confirmScheduleDraft(draft) : await api.confirmDraft(draft);
      state.activeDraft = null;
      processResponse(response);
      showToast(scheduled ? 'تم استلام نتيجة حفظ إعداد الموعد التجريبي.' : 'استلمنا نتيجة العملية من الخدمة المحلية.');
    } catch (error) {
      state.activeDraft = draft;
      renderError(text(error.message, scheduled ? 'تعذر معرفة نتيجة حفظ الموعد.' : 'تعذر معرفة نتيجة التأكيد.'), {
        title: 'النتيجة غير مؤكدة',
        retry: () => recoverDraftStatus(draft),
      });
      appendMessage('system', scheduled
        ? 'لا تعِد الضغط على التأكيد. تحقق من إعداد الموعد الأصلي أولًا.'
        : 'لا تعِد الضغط على تأكيد. تحقق من حالة العملية الأصلية أولًا.');
      showToast('النتيجة غير مؤكدة؛ تحقق من السجل الأصلي.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function cancelDraft(draft, confirmButton, cancelButton) {
    if (state.busy || !state.activeDraft || state.activeDraft.id !== draft.id) return;
    const scheduled = isScheduledDraft(draft);
    confirmButton.disabled = true;
    cancelButton.disabled = true;
    setBusy(true, 'جارِ إلغاء المراجعة…');
    renderLoading(scheduled ? 'جارِ إلغاء إعداد الموعد التجريبي…' : 'جارِ إلغاء مسودة العملية…');
    try {
      const response = scheduled ? await api.cancelScheduleDraft(draft) : await api.cancelDraft(draft);
      state.activeDraft = null;
      processResponse(response);
      if (!responseMessage(response)) appendMessage('assistant', scheduled
        ? 'تم إلغاء مراجعة الموعد التجريبي؛ لم يُحفظ أي إعداد.'
        : 'تم إلغاء المراجعة. لن تُنفّذ هذه المسودة.', []);
      showToast('تم إلغاء المراجعة التجريبية.');
    } catch (error) {
      renderDraft(draft);
      renderError(text(error.message, 'تعذر إلغاء المسودة.'), { retry: () => cancelDraft(draft, confirmButton, cancelButton) });
      showToast('تعذر إلغاء المسودة؛ لم نغيّر العملية من الواجهة.', 'error');
    } finally {
      setBusy(false);
    }
  }

  async function recoverDraftStatus(draftOrId) {
    const active = state.activeDraft;
    const draft = typeof draftOrId === 'object' && draftOrId
      ? draftOrId
      : (active && active.id === draftOrId ? active : { id: draftOrId });
    if (!draft.id || state.busy) return;
    const scheduled = isScheduledDraft(draft);
    setBusy(true, scheduled ? 'جارِ التحقق من إعداد الموعد…' : 'جارِ التحقق من العملية الأصلية…');
    renderLoading(scheduled ? 'جارِ الاستعلام عن إعداد الموعد الأصلي فقط…' : 'جارِ الاستعلام عن المسودة الأصلية فقط…');
    try {
      const response = scheduled ? await api.scheduleDraftStatus(draft.id) : await api.draftStatus(draft.id);
      state.activeDraft = null;
      processResponse(response, { suppressMessage: false });
    } catch (error) {
      renderError(text(error.message, 'تعذر التحقق من حالة المسودة.'), { retry: () => recoverDraftStatus(draft) });
      showToast('لم نتمكن من قراءة الحالة؛ لم نرسل دفعة جديدة.', 'error');
    } finally {
      setBusy(false);
    }
  }
  async function recoverStatus(transactionId, button) {
    if (!transactionId || state.busy) return;
    if (button) button.disabled = true;
    setBusy(true, 'جارِ التحقق من الحالة الأصلية…');
    renderLoading('جارِ الاستعلام عن العملية الأصلية فقط…');
    try {
      const response = await api.transactionStatus(transactionId);
      processResponse(response, { suppressMessage: false });
    } catch (error) {
      renderError(text(error.message, 'تعذر التحقق من الحالة.'), { retry: () => recoverStatus(transactionId) });
      showToast('لم نتمكن من قراءة الحالة؛ لم نرسل دفعة جديدة.', 'error');
    } finally {
      setBusy(false);
    }
  }


  async function loadBootstrap(userId, showLoading) {
    state.scheduleFormConfig = null;
    if (showLoading) renderLoading('جارِ تحميل الجلسة التجريبية…');
    setBusy(true, 'جارِ الاتصال بالخدمة المحلية…');
    try {
      const payload = await api.bootstrap(userId);
      const users = normalizeUsers(payload);
      const session = payload.session || {};
      const selected = session.user_id || payload.user_id || payload.user?.id || payload.user?.user_id || userId || users[0]?.id;
      state.userId = selected || null;
      state.sessionId = session.id || session.session_id || null;
      state.csrfToken = session.csrf_token || session.csrfToken || null;
      state.bootstrapped = Boolean(state.userId && state.sessionId && state.csrfToken);
      renderUsers(users, state.userId);
      renderAccount(payload);
      renderActions(payload.actions || payload.registered_actions || []);
      rememberScheduleForm(payload);
      updateEnvironment(payload);
      renderAgent(payload.agent);
      setJourney('request');
      clearActiveDraft();
      if (payload.welcome_message) appendMessage('assistant', payload.welcome_message, []);
      appendServerMessages(payload.messages);

      if (payload.view) setActive(renderDataCard(payload));
      if (!state.userId) {
        appendMessage('system', 'لم يعُد الخادم جلسة تجريبية صالحة. اختر جلسة أو أعد تشغيل الخدمة.', []);
      }
      setConnection('ready');
    } catch (error) {
      state.bootstrapped = false;
      dom.userSelect.disabled = true;
      dom.input.disabled = true;
      dom.send.disabled = true;
      dom.actionList.replaceChildren(element('p', { className: 'empty-actions', text: 'الخدمات غير متاحة إلى أن يبدأ الخادم المحلي.' }));
      setConnection('offline', 'الخدمة المحلية غير متاحة. لم نستخدم بيانات بديلة أو اتصالًا خارجيًا.');
      renderError(text(error.message, 'تعذر بدء جلسة العرض.'), { title: 'الخدمة المحلية غير متاحة', retry: () => loadBootstrap(FALLBACK_DEMO_USERS[0].id, true) });
    } finally {
      setBusy(false);
      if (state.bootstrapped) {
        dom.input.disabled = false;
        dom.send.disabled = false;
        dom.input.focus();
      }
    }
  }

  function setLargeText(enabled) {
    document.documentElement.classList.toggle('large-text', enabled);
    dom.textSize.setAttribute('aria-pressed', String(enabled));
    dom.textSize.setAttribute('aria-label', enabled ? 'إرجاع حجم النص العادي' : 'تكبير حجم النص');
    dom.textSize.lastElementChild.textContent = enabled ? 'حجم عادي' : 'تكبير النص';
    try { localStorage.setItem('ready-large-text', enabled ? '1' : '0'); } catch (_) { /* optional preference only */ }
  }

  function installEvents() {
    dom.form.addEventListener('submit', submitChat);
    dom.userSelect.addEventListener('change', () => {
      const nextUser = dom.userSelect.value;
      if (!nextUser || nextUser === state.userId) return;
      clearActiveDraft();
      Array.from(dom.conversation.children).filter((node) => !node.matches('[data-welcome]')).forEach((node) => node.remove());
      loadBootstrap(nextUser, true);
    });
    dom.input.addEventListener('input', () => {
      dom.input.style.height = 'auto';
      dom.input.style.height = `${Math.min(dom.input.scrollHeight, 144)}px`;
    });
    dom.input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (dom.form.requestSubmit) dom.form.requestSubmit(); else dom.form.dispatchEvent(new Event('submit', { cancelable: true }));
      }
    });
    dom.textSize.addEventListener('click', () => setLargeText(!document.documentElement.classList.contains('large-text')));
    window.addEventListener('online', () => setConnection('ready'));
    window.addEventListener('offline', () => setConnection('offline', 'الجهاز غير متصل. لم نرسل أي طلب.'));
    try { setLargeText(localStorage.getItem('ready-large-text') === '1'); } catch (_) { setLargeText(false); }
  }

  installEvents();
  loadBootstrap(FALLBACK_DEMO_USERS[0].id, false);
}());
