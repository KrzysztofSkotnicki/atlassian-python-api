import logging
from .rest_client import AtlassianRestAPI


log = logging.getLogger('atlassian.wordpress')


class Wordpress(AtlassianRestAPI):

    def __init__(self, url, username, password, **kwargs):
        kwargs.setdefault('api_root', 'wp-json/wp')
        kwargs.setdefault('api_version', 'v2')
        super(Wordpress, self).__init__(url, username, password, **kwargs)

    def _api_url(self, resource):
        return '/{0}/{1}/{2}'.format(self.api_root, self.api_version, resource)

    # Posts

    def get_posts(self, params=None):
        return self.get(self._api_url('posts'), params=params)

    def get_post(self, post_id):
        return self.get(self._api_url('posts/{0}'.format(post_id)))

    def create_post(self, title, content, status='draft', **kwargs):
        data = {'title': title, 'content': content, 'status': status}
        data.update(kwargs)
        log.info('Creating post "{title}"'.format(title=title))
        return self.post(self._api_url('posts'), data=data)

    def update_post(self, post_id, **kwargs):
        log.info('Updating post {post_id}'.format(post_id=post_id))
        return self.put(self._api_url('posts/{0}'.format(post_id)), data=kwargs)

    def delete_post(self, post_id, force=False):
        log.info('Deleting post {post_id}'.format(post_id=post_id))
        path = self._api_url('posts/{0}'.format(post_id))
        if force:
            path += '?force=true'
        return self.delete(path)

    # Pages

    def get_pages(self, params=None):
        return self.get(self._api_url('pages'), params=params)

    def get_page(self, page_id):
        return self.get(self._api_url('pages/{0}'.format(page_id)))

    def create_page(self, title, content, status='draft', **kwargs):
        data = {'title': title, 'content': content, 'status': status}
        data.update(kwargs)
        log.info('Creating page "{title}"'.format(title=title))
        return self.post(self._api_url('pages'), data=data)

    def update_page(self, page_id, **kwargs):
        log.info('Updating page {page_id}'.format(page_id=page_id))
        return self.put(self._api_url('pages/{0}'.format(page_id)), data=kwargs)

    def delete_page(self, page_id, force=False):
        log.info('Deleting page {page_id}'.format(page_id=page_id))
        path = self._api_url('pages/{0}'.format(page_id))
        if force:
            path += '?force=true'
        return self.delete(path)

    # Categories

    def get_categories(self, params=None):
        return self.get(self._api_url('categories'), params=params)

    def get_category(self, category_id):
        return self.get(self._api_url('categories/{0}'.format(category_id)))

    def create_category(self, name, **kwargs):
        data = {'name': name}
        data.update(kwargs)
        log.info('Creating category "{name}"'.format(name=name))
        return self.post(self._api_url('categories'), data=data)

    # Tags

    def get_tags(self, params=None):
        return self.get(self._api_url('tags'), params=params)

    def create_tag(self, name, **kwargs):
        data = {'name': name}
        data.update(kwargs)
        log.info('Creating tag "{name}"'.format(name=name))
        return self.post(self._api_url('tags'), data=data)

    # Users

    def get_users(self, params=None):
        return self.get(self._api_url('users'), params=params)

    def get_current_user(self):
        return self.get(self._api_url('users/me'))

    # Media

    def get_media(self, params=None):
        return self.get(self._api_url('media'), params=params)

    def get_media_item(self, media_id):
        return self.get(self._api_url('media/{0}'.format(media_id)))

    # Comments

    def get_comments(self, params=None):
        return self.get(self._api_url('comments'), params=params)

    def get_comment(self, comment_id):
        return self.get(self._api_url('comments/{0}'.format(comment_id)))

    def create_comment(self, post_id, content, **kwargs):
        data = {'post': post_id, 'content': content}
        data.update(kwargs)
        log.info('Creating comment on post {post_id}'.format(post_id=post_id))
        return self.post(self._api_url('comments'), data=data)
