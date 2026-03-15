resource "aws_security_group" "msk" {
  name        = "supply-chain-msk-sg-${var.environment}"
  description = "Security group for MSK Kafka"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 9092
    to_port         = 9096
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
    description     = "Kafka from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "supply-chain-msk-sg-${var.environment}" }
}

resource "aws_msk_configuration" "main" {
  name              = "supply-chain-kafka-${var.environment}"
  kafka_versions    = [var.kafka_version]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=3
    min.insync.replicas=2
    num.io.threads=8
    num.network.threads=5
    num.partitions=6
    num.replica.fetchers=2
    replica.lag.time.max.ms=30000
    socket.receive.buffer.bytes=102400
    socket.request.max.bytes=104857600
    socket.send.buffer.bytes=102400
    unclean.leader.election.enable=false
    log.retention.hours=168
    log.segment.bytes=1073741824
    log.retention.check.interval.ms=300000
    zookeeper.session.timeout.ms=18000
  PROPERTIES
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "supply-chain-${var.environment}"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.number_of_broker_nodes

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  client_authentication {
    sasl {
      iam = true
    }
    tls {}
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  enhanced_monitoring = "PER_TOPIC_PER_BROKER"

  open_monitoring {
    prometheus {
      jmx_exporter { enabled_in_broker = true }
      node_exporter { enabled_in_broker = true }
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/aws/msk/supply-chain-${var.environment}"
      }
    }
  }

  tags = { Name = "supply-chain-kafka-${var.environment}" }
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/supply-chain-${var.environment}"
  retention_in_days = 30
}
