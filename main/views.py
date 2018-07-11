import logging
try:
    from urllib2 import HTTPError
except ImportError:
    from urllib.error import HTTPError

from django.conf import settings
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.views import generic
from .forms import FileUploadForm

import ohapi

from .helpers import oh_code_to_member, oh_client_info

logger = logging.getLogger(__name__)

OH_BASE_URL = settings.OPENHUMANS_OH_BASE_URL
OH_API_BASE = OH_BASE_URL + '/api/direct-sharing'
OH_DIRECT_UPLOAD = OH_API_BASE + '/project/files/upload/direct/'
OH_DIRECT_UPLOAD_COMPLETE = OH_API_BASE + '/project/files/upload/complete/'

OH_OAUTH2_REDIRECT_URI = '{}/complete'.format(settings.OPENHUMANS_APP_BASE_URL)


def delete_file(request, file_id):
    """
    Delete specified file in Open Humans for this project member.
    """
    if request.user.is_authenticated and request.user.username != 'admin':
        oh_member = request.user.openhumansmember
        ohapi.api.delete_files(
            project_member_id=oh_member.oh_id,
            access_token=oh_member.get_access_token(**oh_client_info()),
            file_id=file_id)
        return redirect('list')
    return redirect('index')


def delete_all_oh_files(oh_member):
    """
    Delete all current project files in Open Humans for this project member.
    """
    ohapi.api.delete_files(
        project_member_id=oh_member.oh_id,
        access_token=oh_member.get_access_token(**oh_client_info()),
        all_files=True)


def get_auth_url():
    if settings.OPENHUMANS_CLIENT_ID and settings.OPENHUMANS_REDIRECT_URI:
        auth_url = ohapi.api.oauth2_auth_url(
            client_id=settings.OPENHUMANS_CLIENT_ID,
            redirect_uri=settings.OPENHUMANS_REDIRECT_URI)
    else:
        auth_url = ''
    return auth_url


def index(request):
    """
    Starting page for app.
    """
    auth_url = get_auth_url()
    if not auth_url:
        messages.info(request,
                      mark_safe(
                          '<b>You need to set up your ".env"'
                          ' file!</b>'))
    context = {'auth_url': auth_url}
    if request.user.is_authenticated:
        return redirect('overview')
    return render(request, 'main/index.html', context=context)


def overview(request):
    if request.user.is_authenticated:
        oh_member = request.user.openhumansmember
        context = {'oh_id': oh_member.oh_id,
                   'oh_member': oh_member}
        return render(request, 'main/overview.html', context=context)
    return redirect('index')


def login_member(request):
    code = request.GET.get('code', '')
    try:
        oh_member = oh_code_to_member(code=code)
    except Exception:
        oh_member = None
    if oh_member:
        # Log in the user.
        user = oh_member.user
        login(request, user,
              backend='django.contrib.auth.backends.ModelBackend')


def complete(request):
    """
    Receive user from Open Humans. Store data, start data upload task.
    """
    logger.debug("Received user returning from Open Humans.")

    login_member(request)
    if not request.user.is_authenticated:
        logger.debug('Invalid code exchange. User returned to start page.')
        return redirect('/')
    else:
        return redirect('overview')


def logout_user(request):
    """
    Logout user
    """
    if request.method == 'POST':
        logout(request)
    return redirect('index')


def list_files(request):
    if request.user.is_authenticated:
        oh_member = request.user.openhumansmember
        data = ohapi.api.exchange_oauth2_member(
                    oh_member.get_access_token(**oh_client_info()))
        context = {'files': data['data']}
        return render(request, 'main/list.html',
                      context=context)
    return redirect('index')


class upload(generic.FormView):
    form_class = FileUploadForm
    success_url = 'index'
    not_authorized_url = 'index'
    template_name = 'main/upload.html'

    def post(self, request):
        if request.user.is_authenticated:
            form = self.form_class(request.POST, request.FILES)
            desc = form.get_description()
            tags = form.get_tags().split(',')
            filehandle = form.get_file()
            stream = filehandle.file
            oh_member = request.user.openhumansmember
            if filehandle is not None:
                metadata = {'tags': tags,
                            'description': desc}
                file_identifier = None
                oh_member.upload(stream, filehandle.name, metadata,
                                 file_identifier)
            return redirect(self.success_url)
        return redirect(self.not_authorized_url)
