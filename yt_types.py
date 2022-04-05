from typing import TypedDict, Literal, List


class Thumbnail(TypedDict, total=False):
    url: str
    width: int
    height: int


class ThumbnailKeys(TypedDict, total=False):
    default: Thumbnail
    medium: Thumbnail
    high: Thumbnail
    standard: Thumbnail
    maxres: Thumbnail


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


class PlaylistItemResourceId(TypedDict, total=False):
    kind: str
    videoId: str


class PlaylistItemSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: ThumbnailKeys
    channelTitle: str
    videoOwnerChannelTitle: str
    videoOwnerChannelId: str
    playlistId: str
    position: int
    resourceId: PlaylistItemResourceId


class PlaylistItemContentDetails(TypedDict, total=False):
    videoId: str
    startAt: str
    endAt: str
    note: str
    videoPublishedAt: str


class PlaylistItemStatus(TypedDict, total=False):
    privacyStatus: str


class YouTubePlaylistItem(TypedDict, total=False):
    kind: Literal['youtube#playlistItem']
    etag: str
    id: str
    snippet: PlaylistItemSnippet
    contentDetails: PlaylistItemContentDetails
    status: PlaylistItemStatus


class VideoLocalization(TypedDict, total=False):
    title: str
    description: str


class VideoLocalizationKeys(TypedDict, total=False):
    pass


class VideoSnippet(TypedDict, total=False):
    publishedAt: str
    channelId: str
    title: str
    description: str
    thumbnails: ThumbnailKeys
    channelTitle: str
    tags: List[str]
    categoryId: str
    liveBroadcastContent: str
    defaultLanguage: str
    localized: VideoLocalization
    defaultAudioLanguage: str


class VideoRegionRestriction(TypedDict, total=False):
    pass


class VideoContentRating(TypedDict, total=False):
    pass


class VideoContentDetails(TypedDict, total=False):
    pass


class VideoStatus(TypedDict, total=False):
    pass


class VideoStatistics(TypedDict, total=False):
    pass


class VideoPlayer(TypedDict, total=False):
    pass


class VideoTopicDetails(TypedDict, total=False):
    pass


class VideoRecordingDetails(TypedDict, total=False):
    pass


class VideoFileDetails(TypedDict, total=False):
    pass


class VideoVideoStreams(TypedDict, total=False):
    pass


class VideoAudioStreams(TypedDict, total=False):
    pass


class VideoProcessingDetails(TypedDict, total=False):
    pass


class VideoProcessingProgress(TypedDict, total=False):
    pass


class VideoSuggestions(TypedDict, total=False):
    pass


class VideoTagSuggestion(TypedDict, total=False):
    pass


class VideoLiveStreamingDetails(TypedDict, total=False):
    pass


class YouTubeVideo(TypedDict, total=False):
    kind: Literal['youtube#video']
    etag: str
    id: str
    snippet: VideoSnippet
    contentDetails: VideoContentDetails
    status: VideoStatus
    statistics: VideoStatistics
    player: VideoPlayer
    topicDetails: VideoTopicDetails
    recordingDetails: VideoRecordingDetails
    fileDetails: VideoFileDetails
    processingDetails: VideoProcessingDetails
    suggestions: VideoSuggestions
    liveStreamingDetails: VideoLiveStreamingDetails
    localizations: VideoLocalizationKeys
