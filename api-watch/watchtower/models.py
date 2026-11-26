from django.db import models


class Target(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=160)
    spec = models.JSONField(default=dict)
    baseline = models.JSONField(default=dict)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_success = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class CheckRun(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="runs")
    checked_at = models.DateTimeField()
    status = models.CharField(max_length=16)
    http_status = models.IntegerField(null=True)
    duration_ms = models.FloatField()
    data_at = models.DateTimeField(null=True)
    record_count = models.IntegerField(null=True)
    checks = models.JSONField(default=list)
    schema_diff = models.JSONField(default=list)
    error = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=16, default="live")

    class Meta:
        ordering = ["-checked_at"]
        indexes = [models.Index(fields=["target", "-checked_at"])]


class Incident(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name="incidents")
    key = models.CharField(max_length=220)
    kind = models.CharField(max_length=40)
    severity = models.CharField(max_length=16)
    message = models.CharField(max_length=500)
    opened_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    occurrences = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["target", "resolved_at"])]


class Lease(models.Model):
    name = models.CharField(primary_key=True, max_length=32)
    token = models.CharField(max_length=64, blank=True)
    until = models.DateTimeField(null=True)


class DailyBrief(models.Model):
    date = models.DateField(unique=True)
    item_id = models.CharField(max_length=250)
    created_at = models.DateTimeField()
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-date"]
