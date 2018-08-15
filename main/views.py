import json
import logging
try:
    from urllib2 import HTTPError
except ImportError:
    from urllib.error import HTTPError

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.safestring import mark_safe

import ohapi
import requests
from openhumans.models import OpenHumansMember


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
            access_token=oh_member.get_access_token(),
            file_id=file_id)
        return redirect('list')
    return redirect('index')


def delete_all_oh_files(oh_member):
    """
    Delete all current project files in Open Humans for this project member.
    """
    ohapi.api.delete_files(
        project_member_id=oh_member.oh_id,
        access_token=oh_member.get_access_token(),
        all_files=True)


def raise_http_error(url, response, message):
    raise HTTPError(url, response.status_code, message, hdrs=None, fp=None)


def upload_file_to_oh(oh_member, filehandle, metadata):
    """
    This demonstrates using the Open Humans "large file" upload process.
    The small file upload process is simpler, but it can time out. This
    alternate approach is required for large files, and still appropriate
    for small files.
    This process is "direct to S3" using three steps: 1. get S3 target URL from
    Open Humans, 2. Perform the upload, 3. Notify Open Humans when complete.
    """
    # Get the S3 target from Open Humans.
    upload_url = '{}?access_token={}'.format(
        OH_DIRECT_UPLOAD, oh_member.get_access_token())
    req1 = requests.post(upload_url,
                         data={'project_member_id': oh_member.oh_id,
                               'filename': filehandle.name,
                               'metadata': json.dumps(metadata)})
    if req1.status_code != 201:
        raise raise_http_error(upload_url, req1,
                               'Bad response when starting file upload.')

    # Upload to S3 target.
    req2 = requests.put(url=req1.json()['url'], data=filehandle)
    if req2.status_code != 200:
        raise raise_http_error(req1.json()['url'], req2,
                               'Bad response when uploading to target.')

    # Report completed upload to Open Humans.
    complete_url = ('{}?access_token={}'.format(
        OH_DIRECT_UPLOAD_COMPLETE, oh_member.get_access_token()))
    req3 = requests.post(complete_url,
                         data={'project_member_id': oh_member.oh_id,
                               'file_id': req1.json()['id']})
    if req3.status_code != 200:
        raise raise_http_error(complete_url, req2,
                               'Bad response when completing upload.')


def index(request):
    """
    Starting page for app.
    """
    auth_url = OpenHumansMember.get_auth_url()
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


def logout_user(request):
    """
    Logout user
    """
    if request.method == 'POST':
        logout(request)
    return redirect('index')


def upload(request):
    if request.method == 'POST':
        desc = request.POST['file_desc']
        tags = request.POST['file_tags'].split(',')
        uploaded_file = request.FILES.get('data_file')
        if uploaded_file is not None:
            metadata = {'tags': tags,
                        'description': desc}
            upload_file_to_oh(
                request.user.openhumansmember,
                uploaded_file,
                metadata)
        return redirect('index')
    else:
        if request.user.is_authenticated:
            return render(request, 'main/upload.html')
    return redirect('index')


def list_files(request):
    if request.user.is_authenticated:
        oh_member = request.user.openhumansmember
        data = ohapi.api.exchange_oauth2_member(
                    oh_member.get_access_token())
        context = {'files': data['data']}
        return render(request, 'main/list.html',
                      context=context)
    return redirect('index')
