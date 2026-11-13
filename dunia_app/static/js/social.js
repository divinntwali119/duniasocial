(() => {
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (!link || link.hasAttribute('download') || link.matches('[data-share-url], [data-open-comments]') || (link.target && link.target !== '_self')) return;

    let destination;
    try {
      destination = new URL(link.href, window.location.href);
    } catch {
      return;
    }
    if (destination.origin !== window.location.origin) return;
    if (destination.pathname === window.location.pathname && destination.search === window.location.search && destination.hash) return;

    try {
      window.sessionStorage.setItem('dunia-navigation-started', '1');
    } catch (_) {}
    document.documentElement.classList.add('page-navigation-pending');
    window.setTimeout(() => document.documentElement.classList.remove('page-navigation-pending'), 2000);
  });

  const setButtonBusy = (button, busy, loadingLabel = 'Chargement…') => {
    if (!button) return;
    button.disabled = busy;
    button.setAttribute('aria-busy', busy ? 'true' : 'false');
    const label = button.querySelector('[data-button-label]');
    const spinner = button.querySelector('[data-loading-spinner]');
    if (busy) {
      if (label) {
        button.dataset.originalLabel = label.textContent;
        label.textContent = loadingLabel;
      }
      spinner?.classList.remove('hidden');
    } else {
      if (label && button.dataset.originalLabel) {
        label.textContent = button.dataset.originalLabel;
        delete button.dataset.originalLabel;
      }
      spinner?.classList.add('hidden');
    }
  };

  const sendJsonForm = async (form) => {
    const response = await fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        Accept: 'application/json',
      },
      credentials: 'same-origin',
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.message || 'Impossible d’enregistrer votre action. Réessayez.');
      error.payload = payload;
      throw error;
    }
    return payload;
  };

  const setStatus = (element, message) => {
    if (element) element.textContent = message;
  };

  const clearImagePreview = (form) => {
    const preview = form.querySelector('[data-image-preview]');
    const image = preview?.querySelector('[data-image-preview-image]');
    if (preview?.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
    if (preview) {
      preview.hidden = true;
      preview.classList.add('hidden');
      delete preview.dataset.objectUrl;
    }
    if (image) image.removeAttribute('src');
    const fileInput = form.querySelector('[data-post-image-input]');
    if (fileInput) fileInput.value = '';
    const name = preview?.querySelector('[data-image-preview-name]');
    if (name) name.textContent = '';
  };

  const submitLike = async (form) => {
    const button = form.querySelector('button[type="submit"]');
    const status = form.closest('article')?.querySelector('[data-interaction-status]');
    if (!button || button.disabled) return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try {
      const { is_liked: isLiked, likes_count: likesCount } = await sendJsonForm(form);
      button.setAttribute('aria-pressed', String(isLiked));
      button.classList.toggle('text-primary', isLiked);
      button.classList.toggle('text-base-content/70', !isLiked);
      button.classList.toggle('hover:text-base-content', !isLiked);
      const likeIcon = button.querySelector('[data-like-icon]');
      likeIcon?.classList.toggle('text-primary', isLiked);
      likeIcon?.classList.toggle('text-base-content/45', !isLiked);
      likeIcon?.setAttribute('fill', isLiked ? 'currentColor' : 'none');
      likeIcon?.setAttribute('stroke', isLiked ? 'none' : 'currentColor');
      const count = button.querySelector('[data-like-count]');
      if (count) count.textContent = String(likesCount);
      setStatus(status, isLiked ? 'Publication aimée.' : 'Mention J’aime retirée.');
    } catch (error) {
      setStatus(status, error.message || 'Impossible de modifier votre réaction.');
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  };

  const submitComment = async (form, button) => {
    const details = form.closest('details');
    const status = details?.querySelector('[data-comments-status]');
    const interactionStatus = form.closest('article')?.querySelector('[data-interaction-status]');
    const textarea = form.querySelector('textarea[name="contenu"]');
    if (!textarea?.value.trim()) {
      textarea?.focus();
      return;
    }

    setButtonBusy(button, true, button?.dataset.loadingLabel || 'Envoi…');
    try {
      const { comment, comment_count: commentCount } = await sendJsonForm(form);
      const list = details?.querySelector('[data-comments-list]');
      if (list && comment) {
        list.querySelector('[data-comments-empty]')?.remove();
        const row = document.createElement('div');
        row.className = 'flex items-start gap-2';
        row.setAttribute('data-comment-item', '');

        const avatar = document.createElement('img');
        avatar.src = comment.avatar_url;
        avatar.alt = '';
        avatar.loading = 'lazy';
        avatar.className = 'mt-1 h-8 w-8 shrink-0 rounded-full border border-base-300 object-cover';

        const bubble = document.createElement('div');
        bubble.className = 'min-w-0 rounded-2xl bg-base-200/70 px-3 py-2';
        const author = document.createElement('a');
        author.href = comment.author_url;
        author.className = 'text-sm font-semibold hover:underline';
        author.textContent = comment.author;
        const content = document.createElement('p');
        content.className = 'mt-1 whitespace-pre-line text-sm';
        content.textContent = comment.content;
        const date = document.createElement('span');
        date.className = 'mt-1 block text-xs text-base-content/55';
        date.textContent = comment.created_at;
        bubble.append(author, content, date);
        row.append(avatar, bubble);
        list.append(row);
      }

      const count = form.closest('article')?.querySelector('[data-comment-count]');
      if (count) count.textContent = String(commentCount);
      if (textarea) {
        textarea.value = '';
        textarea.style.height = '';
      }
      setStatus(status, 'Commentaire publié.');
      setStatus(interactionStatus, 'Commentaire publié.');
    } catch (error) {
      setStatus(status, error.message || 'Impossible d’ajouter le commentaire.');
    } finally {
      setButtonBusy(button, false);
    }
  };

  const recordShare = async (shareLink) => {
    const csrfCookie = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    const endpoint = shareLink.dataset.shareEndpoint;
    if (!endpoint || !csrfCookie) return;

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'X-CSRFToken': decodeURIComponent(csrfCookie[1]),
          Accept: 'application/json',
        },
        credentials: 'same-origin',
      });
      if (!response.ok) return;

      const { shares_count: sharesCount } = await response.json();
      const card = shareLink.closest('article');
      const count = card?.querySelector('[data-share-count]');
      const word = card?.querySelector('[data-share-count-word]');
      const label = card?.querySelector('[data-share-count-label]');
      if (count) count.textContent = String(sharesCount);
      if (word) word.textContent = sharesCount === 1 ? 'partage' : 'partages';
      if (label) label.setAttribute('aria-label', `Nombre de partages : ${sharesCount}`);
    } catch {
      // Le partage reste effectué même si le compteur ne peut pas être actualisé.
    }
  };

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;

    if (form.matches('[data-feed-like]')) {
      event.preventDefault();
      await submitLike(form);
      return;
    }

    if (form.matches('[data-feed-comment]')) {
      event.preventDefault();
      await submitComment(form, event.submitter || form.querySelector('button[type="submit"]'));
      return;
    }

    if (form.matches('[data-social-post-form]')) {
      event.preventDefault();
      const button = event.submitter || form.querySelector('button[type="submit"]');
      const status = form.querySelector('[data-post-status]');
      if (!button || button.disabled) return;
      setButtonBusy(button, true, button.dataset.loadingLabel || 'Publication…');
      try {
        const { message } = await sendJsonForm(form);
        const errors = form.querySelector('[data-post-errors]');
        if (errors) errors.replaceChildren();
        form.reset();
        clearImagePreview(form);
        const successMessage = message || 'Votre publication a été ajoutée au fil.';
        setStatus(status, successMessage);
        setStatus(document.querySelector('[data-post-announcement]'), successMessage);
        const composer = form.closest('[data-post-composer]');
        if (composer) composer.open = false;
        const query = `${window.location.pathname}${window.location.search}`;
        await fetchFeedPage(query, true);
      } catch (error) {
        setStatus(status, error.message || 'Impossible de publier. Réessayez.');
        const errors = form.querySelector('[data-post-errors]');
        const details = error.payload?.errors;
        if (errors && details) {
          const messages = Object.values(details).flatMap((fieldErrors) => fieldErrors.map((fieldError) => fieldError.message));
          errors.replaceChildren(...messages.map((messageText) => {
            const line = document.createElement('span');
            line.className = 'block';
            line.textContent = messageText;
            return line;
          }));
        }
      } finally {
        setButtonBusy(button, false);
      }
      return;
    }

    if (!form.matches('[data-loading-form]')) return;
    const button = event.submitter || form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    setButtonBusy(button, true, button.dataset.loadingLabel || 'Envoi…');
  });

  document.addEventListener('change', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches('[data-post-image-input]')) return;
    const file = input.files?.[0];
    const form = input.closest('[data-social-post-form]');
    const preview = form?.querySelector('[data-image-preview]');
    const image = preview?.querySelector('[data-image-preview-image]');
    const name = preview?.querySelector('[data-image-preview-name]');
    if (!file || !preview || !image) return;
    if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
    const objectUrl = URL.createObjectURL(file);
    preview.dataset.objectUrl = objectUrl;
    image.src = objectUrl;
    if (name) name.textContent = file.name;
    preview.hidden = false;
    preview.classList.remove('hidden');
  });

  document.addEventListener('input', (event) => {
    const textarea = event.target;
    if (!(textarea instanceof HTMLTextAreaElement) || !textarea.matches('[data-autosize]')) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 240)}px`;
  });

  document.addEventListener('click', async (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const dialogOpener = target.closest('[data-dialog-open]');
    if (dialogOpener) {
      const dialog = document.querySelector(dialogOpener.dataset.dialogOpen);
      if (dialog instanceof HTMLDialogElement && !dialog.open) dialog.showModal();
    }

    if (target instanceof HTMLDialogElement && target.hasAttribute('data-dismissible-dialog') && event.target === target) {
      target.close();
    }

    const removeImageButton = target.closest('[data-remove-image]');
    if (removeImageButton) {
      const form = removeImageButton.closest('[data-social-post-form]');
      if (form) clearImagePreview(form);
    }

    const commentButton = target.closest('[data-open-comments]');
    if (commentButton) {
      const target = document.getElementById(commentButton.dataset.openComments);
      if (target instanceof HTMLDetailsElement) {
        target.open = true;
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.querySelector('textarea')?.focus({ preventScroll: true });
      }
    }

    const shareLink = target.closest('[data-share-url]');
    if (shareLink) {
      event.preventDefault();
      const shareData = {
        title: shareLink.dataset.shareTitle || 'Dunia',
        text: shareLink.dataset.shareText || '',
        url: shareLink.dataset.shareUrl,
      };
      try {
        if (navigator.share) {
          await navigator.share(shareData);
          void recordShare(shareLink);
        } else if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(shareData.url);
          void recordShare(shareLink);
          const label = shareLink.querySelector('[data-share-action-label]');
          if (label) {
            const previousText = label.textContent;
            label.textContent = 'Lien copié';
            window.setTimeout(() => { label.textContent = previousText; }, 1800);
          }
        } else {
          window.location.assign(shareData.url);
        }
      } catch (error) {
        if (error?.name !== 'AbortError') window.location.assign(shareData.url);
      }
    }
  });

  const feedList = document.getElementById('feed-list');
  const loadMoreButton = document.querySelector('[data-feed-load-more]');
  const refreshButton = document.querySelector('[data-feed-refresh]');
  const feedStatus = document.getElementById('feed-status');
  const skeletonTemplate = document.getElementById('feed-skeleton-template');

  if (!feedList || !loadMoreButton || !refreshButton || !skeletonTemplate) return;

  const showSkeletons = () => {
    const placeholders = document.createDocumentFragment();
    for (let index = 0; index < 2; index += 1) {
      const card = skeletonTemplate.content.firstElementChild.cloneNode(true);
      card.dataset.feedSkeleton = 'true';
      placeholders.append(card);
    }
    feedList.append(placeholders);
  };

  const removeSkeletons = () => {
    feedList.querySelectorAll('[data-feed-skeleton]').forEach((card) => card.remove());
  };

  const fetchFeedPage = async (url, replace) => {
    const button = replace ? refreshButton : loadMoreButton;
    const previousHtml = replace ? feedList.innerHTML : '';
    feedList.setAttribute('aria-busy', 'true');
    feedStatus.textContent = '';
    showSkeletons();
    const skeletonTimeout = window.setTimeout(removeSkeletons, 2000);
    setButtonBusy(button, true, replace ? 'Actualisation…' : 'Chargement…');

    try {
      const requestUrl = new URL(url, window.location.href);
      requestUrl.searchParams.set('feed_fragment', '1');
      if (replace) requestUrl.searchParams.set('_', String(Date.now()));
      const response = await fetch(requestUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('Impossible de charger le fil.');
      const html = await response.text();
      const parsed = new DOMParser().parseFromString(html, 'text/html');
      const nextPage = parsed.querySelector('[data-feed-page]');
      if (!nextPage) throw new Error('La réponse du fil est invalide.');
      if (replace) {
        feedList.replaceChildren(document.importNode(nextPage, true));
      } else {
        const page = feedList.querySelector('[data-feed-page]');
        page?.insertAdjacentHTML('beforeend', nextPage.innerHTML);
      }
      loadMoreButton.dataset.nextUrl = nextPage.dataset.nextUrl || '';
      const hasNext = nextPage.dataset.hasNext === 'true' && Boolean(nextPage.dataset.nextUrl);
      loadMoreButton.hidden = !hasNext;
      refreshButton.hidden = hasNext;
      feedStatus.textContent = replace ? 'Le fil a été actualisé.' : 'Publications chargées.';
    } catch (error) {
      if (replace && previousHtml) feedList.innerHTML = previousHtml;
      feedStatus.textContent = error.message || 'Une erreur est survenue. Réessayez.';
    } finally {
      window.clearTimeout(skeletonTimeout);
      removeSkeletons();
      feedList.setAttribute('aria-busy', 'false');
      setButtonBusy(button, false);
    }
  };

  loadMoreButton.addEventListener('click', () => {
    if (loadMoreButton.dataset.nextUrl) fetchFeedPage(loadMoreButton.dataset.nextUrl, false);
  });
  refreshButton.addEventListener('click', () => fetchFeedPage(`${window.location.pathname}${window.location.search}`, true));
})();
