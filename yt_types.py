from typing import TypedDict, Literal


class Thumbnail(TypedDict, total=False):
    url: str
    width: int
    height: int


class ThumbnailKeys(TypedDict, total=False):
    default: Thumbnail
    medium: Thumbnail
    high: Thumbnail


class BroadcastSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: ThumbnailKeys
    scheduledStartTime: str
    scheduledEndTime: str
    actualStartTime: str
    actualEndTime: str
    isDefaultBroadcast: bool
    liveChatId: str


class BroadcastStatus(TypedDict, total=False):
    lifeCycleStatus: str
    privacyStatus: str
    recordingStatus: str
    madeForKids: str
    selfDeclaredMadeForKids: str


class BroadcastMonitorStream(TypedDict, total=False):
    enableMonitorStream: bool
    broadcastStreamDelayMs: int
    embedHtml: str


class BroadcastContentDetails(TypedDict, total=False):
    boundStreamId: str
    boundStreamLastUpdateTimeMs: str
    monitorStream: BroadcastMonitorStream
    enableEmbed: bool
    enableDvr: bool
    enableContentEncryption: bool
    startWithSlate: bool
    recordFromStart: bool
    enableClosedCaptions: bool
    closedCaptionsType: str
    projection: str
    enableLowLatency: bool
    latencyPreference: bool
    enableAutoStart: bool
    enableAutoStop: bool


class BroadcastStatistics(TypedDict, total=False):
    totalChatCount: int


class YouTubeLiveBroadcast(TypedDict, total=False):
    kind: Literal['youtube#liveBroadcast']
    etag: str
    id: str
    snippet: BroadcastSnippet
    status: BroadcastStatus
    contentDetails: BroadcastContentDetails
    statistics: BroadcastStatistics
