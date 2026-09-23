##############################################################################
# Copyright 2022 SoundHound, Incorporated.  All rights reserved.
##############################################################################
import base64
import hashlib
import hmac
import http.client
import ssl
import json
import threading
import time
import socket
import uuid
import urllib.parse
import struct
import gzip
from typing import Optional, Dict
from types import MappingProxyType

try:
    import pySHSpeex
except ImportError:
    pass



TEXT_ENDPOINT = "https://api.houndify.com/v1/text"
VOICE_ENDPOINT = "https://api.houndify.com/v1/audio"
TRANSCRIPTION_ENDPOINT = "https://transcription.houndify.com/v1/transcription"
VERSION = "2.1.4"

# NOTE: unverified SSL context -- this environment's system CA bundle fails to
# validate api.houndify.com's certificate chain (SSLCertVerificationError:
# unable to get local issuer certificate). Bypasses cert verification for the
# Houndify HTTPS connections below; revisit if this SDK is deployed somewhere
# with a working CA bundle instead of patching around it.
_UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()


class HoundifySDKError(Exception):
    def __init__(self, message = ""):
        super(HoundifySDKError, self).__init__(message)



class HoundifyTimeoutError(HoundifySDKError):
    def __init__(self, other):
        super(HoundifyTimeoutError, self).__init__(other)



class _BaseHoundClient(object):

    def __init__(
        self,
        clientID,
        clientKey,
        userID,
        endpoint,
        proxyHost,
        proxyPort,
        proxyHeaders,
        timeout,
        saveQuery,
        headers: Optional[Dict[str, str]] = None
    ):
        self.clientID = clientID
        self.clientKey = base64.urlsafe_b64decode(clientKey)
        self.userID = userID

        endpoint_parse = urllib.parse.urlparse(endpoint)
        self.is_https = endpoint_parse.scheme == "https"
        self.hostname = endpoint_parse.netloc
        self.path = endpoint_parse.path

        self.proxyHost = proxyHost
        self.proxyPort = proxyPort
        self.proxyHeaders = proxyHeaders
        self.gzip = True
        self.timeout = timeout
        self.saveQuery = saveQuery

        self.HoundRequestInfo = {
          "ClientID": clientID,
          "UserID": userID,
          "SDK": "python3",
          "SDKVersion": VERSION
        }
        self.headers = headers


    def setHoundRequestInfo(self, key, value):
        """
        There are various fields in the HoundRequestInfo object that can
        be set to help the server provide the best experience for the client.
        Refer to the Houndify documentation to see what fields are available
        and set them through this method before starting a request
        """
        self.HoundRequestInfo[key] = value


    def removeHoundRequestInfo(self, key):
        """
        Remove request info field through this method before starting a request
        """
        self.HoundRequestInfo.pop(key, None)


    def setLocation(self, latitude, longitude):
        """
        Many domains make use of the client location information to provide
        relevant results.  This method can be called to provide this information
        to the server before starting the request.

        latitude and longitude are floats (not string)
        """
        self.setHoundRequestInfo("Latitude", latitude)
        self.setHoundRequestInfo("Longitude", longitude)



    def setConversationState(self, conversation_state):
        self.setHoundRequestInfo("ConversationState", conversation_state)
        if "ConversationStateTime" in conversation_state:
            self.setHoundRequestInfo("ConversationStateTime", conversation_state["ConversationStateTime"])


    def _generateHeaders(self, requestInfo):
        requestID = str(uuid.uuid4())
        if "RequestID" in requestInfo:
            requestID = requestInfo["RequestID"]

        timestamp = str(int(time.time()))
        if "TimeStamp" in requestInfo:
            timestamp = str(requestInfo["TimeStamp"])

        HoundRequestAuth = self.userID + ";" + requestID
        h = hmac.new(self.clientKey, (HoundRequestAuth + timestamp).encode("utf-8"), hashlib.sha256)
        signature = base64.urlsafe_b64encode(h.digest()).decode("utf-8")
        HoundClientAuth = self.clientID + ";" + timestamp + ";" + signature

        requestInfoString = json.dumps(self.HoundRequestInfo)

        headers = {
          "Hound-Request-Authentication": HoundRequestAuth,
          "Hound-Client-Authentication": HoundClientAuth,
          "Hound-Request-Info-Length": len(requestInfoString)
        }

        if "InputLanguageEnglishName" in requestInfo:
            headers["Hound-Input-Language-English-Name"] = requestInfo["InputLanguageEnglishName"]
        if "InputLanguageIETFTag" in requestInfo:
            headers["Hound-Input-Language-IETF-Tag"] = requestInfo["InputLanguageIETFTag"]

        if self.gzip:
            headers["Hound-Response-Accept-Encoding"] = "gzip"

        if not self.saveQuery:
            headers["Hound-Extra-Options"] = '{"DoNotSave": ["all"], "DoNotLabel": true}'
        if self.headers:
            # use the class attribute to override default headers
            headers.update(self.headers)
        return headers, requestInfoString



class TextHoundClient(_BaseHoundClient):
    """
    TextHoundClient is used for making text queries for Hound
    """
    def __init__(
        self,
        clientID,
        clientKey,
        userID,
        requestInfo = dict(),
        endpoint = TEXT_ENDPOINT,
        proxyHost = None,
        proxyPort = None,
        proxyHeaders = None,
        timeout = None,
        saveQuery = True,
        headers: Optional[Dict[str, str]] = None
    ):

        super().__init__(clientID, clientKey, userID, endpoint, proxyHost, proxyPort, proxyHeaders, timeout, saveQuery,
                         headers=headers)
        self.HoundRequestInfo.update(requestInfo)


    def query(self, query):
        """
        Make a text query to Hound.

        query is the string of the query
        """
        headers, requestInfoString = self._generateHeaders(self.HoundRequestInfo)

        if self.proxyHost:
            conn = http.client.HTTPSConnection(self.proxyHost, self.proxyPort, context=_UNVERIFIED_SSL_CONTEXT)
            conn.set_tunnel(self.hostname, headers = self.proxyHeaders)
        elif self.is_https:
            conn = http.client.HTTPSConnection(self.hostname, context=_UNVERIFIED_SSL_CONTEXT)
        else:
            conn = http.client.HTTPConnection(self.hostname)

        conn.request("POST", self.path + "?query=" + urllib.parse.quote(query), headers = headers, body = requestInfoString)
        resp = conn.getresponse()

        raw_response = resp.read()

        if resp.getheader("Hound-Response-Content-Encoding") == "gzip":
            raw_response = gzip.decompress(raw_response)

        try:
            return json.loads(raw_response.decode("utf-8"))
        except json.JSONDecodeError:
            raise HoundifySDKError(message="Invalid ID or Key")



class HoundListener(object):
    """
    HoundListener is an abstract base class that defines the callbacks
    that can be received while streaming speech to the server
    """
    def onPartialTranscript(self, transcript):
        """
        onPartialTranscript is fired when the server has sent a partial transcript
        in live transcription mode.  "transcript" is a string with the partial transcript.
        """
        pass
    def onPartialTranscriptRaw(self, response):
        """
        onPartialTranscriptRaw is fired when the server has a partial transcript.
        This method gives access to the full Houndify response.
        """
        pass
    def onFinalPartialTranscript(self, transcript):
        """
        onFinalPartialTranscript is fired once the server has identified one or more
        complete sentences that are guaranteed not to change in the future.
        These sentences won't be included in partial transcripts going forward,
        the client needs to accumulate them in order to compile the full transcript.
        Only occurs in live transcription mode.
        """
        pass
    def onPartialTranscriptProperties(self, transcript, props):
        """
        onPartialTranscriptProperties is fired when the server has a partial transcript
        and detailed information is provided by the server (usually in live transcription
        mode). "props" is a HoundTranscriptProperties JSON object (as a Python dict)
        containing the "Tokens" array and optional extra fields such as "TopicIdentification"
        or "EntityDetection".
        """
        pass
    def onFinalPartialTranscriptProperties(self, transcript, props):
        """
        onFinalPartialTranscriptProperties is fired once the server has identified one
        or more complete sentences that are guaranteed not to change in the future.
        These sentences won't be included in partial transcripts going forward,
        the client needs to accumulate them in order to compile the full transcript.
        "props" is a HoundTranscriptProperties JSON object (as a Python dict)
        containing the "Tokens" array and optional extra fields such as "TopicIdentification"
        or "EntityDetection". Only occurs in live transcription mode.
        """
        pass
    def onFinalResponse(self, response):
        """
        onFinalResponse is fired when the server has completed processing the query
        and has a response.  "response" is the JSON object (as a Python dict) which
        the server sends back.
        """
        pass
    def onError(self, err):
        """
        onError is fired if there is an error interacting with the server.  It contains
        the parsed JSON from the server.
        """
        pass


class StreamingHoundClient(_BaseHoundClient):
    """
    StreamingHoundClient is used to send streaming audio to the Hound
    server and receive live transcriptions back
    """
    def __init__(
        self,
        clientID: str,
        clientKey: str,
        userID: str, requestInfo = dict(),
        endpoint: str = VOICE_ENDPOINT,
        sampleRate: int = 16000,
        enableVAD: bool = False,
        useSpeex: bool = False,
        proxyHost = None,
        proxyPort = None,
        proxyHeaders = None,
        timeout = None,
        saveQuery = True,
        headers: Optional[Dict[str, str]] = MappingProxyType({"Transfer-Encoding": "chunked"})

    ):
        """
        clientID and clientKey are "Client ID" and "Client Key"
        from the Houndify.com web site.
        """
        super().__init__(clientID, clientKey, userID, endpoint, proxyHost, proxyPort, proxyHeaders, timeout, saveQuery,
                         headers=headers)

        self.sampleRate = sampleRate
        self.useSpeex = useSpeex
        self.speexFrameSize = int(2 * 0.02 * self.sampleRate) # 20ms 16-bit audio frame = (2 * 0.02 * sampleRate) bytes
        self.enableVAD = enableVAD

        self.setHoundRequestInfo("PartialTranscriptsDesired", True)
        self.HoundRequestInfo.update(requestInfo)


    def setSampleRate(self, sampleRate):
        """
        Override the default sample rate of 16 khz for audio.

        NOTE that only 8 khz and 16 khz are supported
        """
        if sampleRate == 8000 or sampleRate == 16000:
            self.sampleRate = sampleRate
        else:
            raise Exception("Unsupported sample rate")


    def start(self, listener=HoundListener(), isSpeexFile=False):
        """
        This method is used to make the actual connection to the server and prepare
        for audio streaming.

        listener is a HoundListener (or derived class) object
        """
        self.audioFinished = False
        self.lastResult = None
        self.lastException = None
        self.killCallbackThread = False
        self.buffer = bytes()

        try:
            if self.proxyHost:
                self.conn = http.client.HTTPSConnection(self.proxyHost, self.proxyPort, timeout = self.timeout, context=_UNVERIFIED_SSL_CONTEXT)
                self.conn.set_tunnel(self.hostname, headers = self.proxyHeaders)
            elif self.is_https:
                self.conn = http.client.HTTPSConnection(self.hostname, timeout = self.timeout, context=_UNVERIFIED_SSL_CONTEXT)
            else:
                self.conn = http.client.HTTPConnection(self.hostname, timeout = self.timeout)

            self.conn.putrequest("POST", self.path)

            headers, requestInfoString = self._generateHeaders(self.HoundRequestInfo)

            for header in headers:
                self.conn.putheader(header, headers[header])
            self.conn.endheaders()

            self.callbackTID = threading.Thread(target = self._callback, args = (listener,))
            self.callbackTID.start()

            self._send(requestInfoString)

            if isSpeexFile:
                return

            audio_header = self._wavHeader(self.sampleRate)
            if self.useSpeex:
                audio_header = pySHSpeex.Init(self.sampleRate == 8000)
            self._send(audio_header)

        except socket.timeout as e:
            raise HoundifyTimeoutError(e) from e

        except Exception as e:
            raise HoundifySDKError() from e


    def fill(self, data):
        """
        After successfully connecting to the server with start(), pump PCM samples
        through this method.

        data is 16-bit, 8 KHz/16 KHz little-endian PCM samples.
        Returns True if the server detected the end of audio and is processing the data
        or False if the server is still accepting audio
        """
        if self.audioFinished:
            return True

        if self.useSpeex:
            self.buffer += data

            while len(self.buffer) >= self.speexFrameSize:
                frame = self.buffer[:self.speexFrameSize]
                self.buffer = self.buffer[self.speexFrameSize:]
                self._send(pySHSpeex.EncodeFrame(frame))

        else:
            self._send(data)

        return self.audioFinished


    def finish(self):
        """
        Once fill returns True, call finish() to finalize the transaction.  finish will
        wait for all the data to be received from the server.

        After finish() is called, you can start another request with start() but each
        start() call should have a corresponding finish() to wait for the threads
        """

        try:
            try:
                if len(self.buffer) > 0:
                    padding_size = self.speexFrameSize - len(self.buffer)
                    frame = self.buffer + b'\x00' * padding_size
                    self._send(pySHSpeex.EncodeFrame(frame))

                self._send("")

            except socket.timeout as e:
                raise HoundifyTimeoutError(e) from e

            except Exception as e:
                raise HoundifySDKError() from e

            try:
                self.callbackTID.join(self.timeout)
            except KeyboardInterrupt:
                # If join fails to acquire a lock due to the KeyboardInterrupt
                # it will release the lock, stop the thread and then raise
                # the KeyboardInterrupt exception
                pass

            if self.callbackTID.is_alive():
                # join timed out but thread is still running
                self.killCallbackThread = True

                raise HoundifyTimeoutError()
            elif self.lastException is not None:
                if isinstance(self.lastException, socket.timeout):
                    raise HoundifyTimeoutError(self.lastException) from self.lastException
                else:
                    raise HoundifySDKError() from self.lastException
            else:
                return self.lastResult

        finally:
            self._close()


    def _close(self):
        if self.conn is not None:
            try:
                self.conn.close()
                self.conn = None
            except:
                pass


    def _callback(self, listener):
        try:
            gen = self._readline(self.conn.sock)
            self._parseResponse(listener, gen)

        except Exception as e:
            self.lastException = e

        finally:
            self.audioFinished = True


    def _parseResponse(self, listener, gen):
        headers = ""
        body = ""
        is_chunked = False
        chunk_size = None
        content_length = None
        headers_done = False

        while not self.killCallbackThread:
            try:
                line = gen.send(chunk_size)

                # Uses gzip magic numbers to check that the byte chunk is compressed
                if self.gzip and line[:2] == b"\x1f\x8b":
                    line = gzip.decompress(line)

                line = line.decode("utf-8")

                if not headers_done:
                    headers += line + "\r\n"
                    header = line.strip().lower()
                    if header == "transfer-encoding: chunked":
                        is_chunked = True
                    if "content-length" in header:
                        content_length = int(header.split(" ")[1])
                    if headers.endswith("\r\n\r\n"):
                        headers_done = True
                        chunk_size = content_length
                    continue

                body += line

                if is_chunked and chunk_size is None:
                    chunk_size = int(line, 16)
                    continue

                chunk_size = None

                try:
                    parsedMsg = json.loads(line)
                except:
                    raise Exception(body) from None

                if "Status" in parsedMsg and parsedMsg["Status"] == "Error":
                    self.lastResult = parsedMsg
                    listener.onError(parsedMsg)
                    return

                if "Format" in parsedMsg:
                    if parsedMsg["Format"] == "SoundHoundVoiceSearchParialTranscript" or parsedMsg["Format"] == "HoundVoiceQueryPartialTranscript":
                        try:
                            listener.onFinalPartialTranscript(parsedMsg["FinalPartialTranscript"])
                        except:
                            pass
                        try:
                            listener.onFinalPartialTranscriptProperties(parsedMsg["FinalPartialTranscript"], parsedMsg["FinalPartialTranscriptProperties"])
                        except:
                            pass
                        try:
                            listener.onPartialTranscriptProperties(parsedMsg["PartialTranscript"], parsedMsg["PartialTranscriptProperties"])
                            listener.onPartialTranscriptRaw(parsedMsg)
                        except:
                            pass
                        listener.onPartialTranscript(parsedMsg["PartialTranscript"])
                        if self.enableVAD and "SafeToStopAudio" in parsedMsg and parsedMsg["SafeToStopAudio"]:
                            self.audioFinished = True

                    if parsedMsg["Format"] == "SoundHoundVoiceSearchResult" or parsedMsg["Format"] == "HoundQueryResult":
                        self.lastResult = parsedMsg
                        listener.onFinalResponse(parsedMsg)
                        return
            except KeyboardInterrupt:
                self.audioFinished = True
            except socket.error as e:
                raise


    def _wavHeader(self, sampleRate=16000):
        genHeader = "RIFF".encode("UTF-8")
        genHeader += struct.pack("<L", 36) #ChunkSize - dummy
        genHeader += "WAVE".encode("UTF-8")
        genHeader += "fmt ".encode("UTF-8")
        genHeader += struct.pack("<L", 16) #Subchunk1Size
        genHeader += struct.pack("<H", 1)  #AudioFormat - PCM
        genHeader += struct.pack("<H", 1)  #NumChannels
        genHeader += struct.pack("<L", sampleRate) #SampleRate
        genHeader += struct.pack("<L", 8 * sampleRate) #ByteRate
        genHeader += struct.pack("<H", 2) #BlockAlign (num of bytes per sample)
        genHeader += struct.pack("<H", 16) #BitsPerSample
        genHeader += "data".encode("UTF-8")
        genHeader += struct.pack("<L", 0) #Subchunk2Size - dummy

        return genHeader


    def _send(self, msg):
        if self.conn:
            if (isinstance(msg, str)): msg = msg.encode("utf-8")
            chunk_size = "%x\r\n" % len(msg)

            self.conn.send(chunk_size.encode("utf-8"))
            self.conn.send(msg + "\r\n".encode("utf-8"))


    def _readline(self, socket):
        response_buffer = bytearray()
        chunk_size = None
        separator = "\r\n".encode("utf-8")
        msg_size = 4096
        deadline = None

        while not self.killCallbackThread:
            try:
                msg = socket.recv(msg_size)

            except BlockingIOError:
                # When a timeout is set, spurious BlockingIOErrors may occur, which should be ignored.
                # If the read operation had timed out, then a socket.timeout error (which is not a subclass of BlockingIOError)
                # would have occurred instead.
                if deadline is None:
                    deadline = time.time() + self.timeout
                    continue
                else:
                    if time.time() > deadline:
                        # re-raise the exception since the problem has continued past the timeout
                        raise
                    else:
                        # sleep before retrying so that we don't end up in a tight loop spinning
                        # in case something has really gone wrong
                        time.sleep(0.1)
                        continue
            except Exception as e:
                print(f"{e}")

            deadline = None

            if not msg: break

            response_buffer += msg

            while True:
                if chunk_size is not None:
                    if len(response_buffer) < chunk_size + 2: break
                    chunk = response_buffer[:chunk_size]
                    response_buffer = response_buffer[chunk_size + 2:]

                else:
                    split_buffer = response_buffer.split(separator, 1)
                    if len(split_buffer) == 1: break
                    chunk = split_buffer[0]
                    response_buffer = split_buffer[1]

                chunk_size = yield chunk

        if response_buffer: yield response_buffer
