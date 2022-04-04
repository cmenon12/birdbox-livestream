from typing import TypedDict, Literal, List


class BroadcastThumbnail(TypedDict, total=False):
    url: str
    width: int
    height: int


class BroadcastThumbnailKeys(TypedDict, total=False):
    default: BroadcastThumbnail
    medium: BroadcastThumbnail
    high: BroadcastThumbnail


class BroadcastSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: BroadcastThumbnailKeys
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


class PageInfo(TypedDict, total=False):
    totalResults: int
    resultsPerPage: int


class YouTubeLiveBroadcastList(TypedDict, total=False):
    kind: Literal['youtube#liveBroadcastListResponse']
    etag: str
    nextPageToken: str
    prevPageToken: str
    pageInfo: PageInfo
    items: List[YouTubeLiveBroadcast]


class StreamSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    isDefaultStream: bool


class StreamIngestionInfo(TypedDict, total=False):
    streamName: str
    ingestionAddress: str
    backupIngestionAddress: str


class StreamCdn(TypedDict, total=False):
    ingestionType: str
    ingestionInfo: StreamIngestionInfo
    resolution: str
    frameRate: str


class StreamConfigurationIssue(TypedDict, total=False):
    type: str
    severity: str
    reason: str
    description: str


class StreamHealthStatus(TypedDict, total=False):
    status: str
    lastUpdateTimeSeconds: int
    configurationIssues: List[StreamConfigurationIssue]


class StreamStatus(TypedDict, total=False):
    streamStatus: str
    healthStatus: StreamHealthStatus


class StreamContentDetails(TypedDict, total=False):
    closedCaptionsIngestionUrl: str
    isReusable: bool


class YouTubeLiveStream(TypedDict, total=False):
    kind: Literal['youtube#liveStream']
    etag: str
    id: str
    snippet: StreamSnippet
    cdn: StreamCdn
    status: StreamStatus
    contentDetails: StreamContentDetails